"""
Dashboard endpoints — lightweight status summaries.

GET /dashboard/sla-default-summary        — status counts (default/user override SLA)
GET /dashboard/sla-history-summary        — status counts using SLA history (median) for a date range
GET /dashboard/weekly-status-sla-default  — week-wise status counts (default/user override SLA)
GET /dashboard/weekly-status-sla-history  — week-wise status counts (SLA history-based)
"""

import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.services.gantt import get_dashboard_summary
from app.services.gantt.milestones import (
    get_user_expected_days_overrides,
    get_history_expected_days_by_user,
    save_user_history_expected_days,
)
from app.services.weekly_status import get_weekly_status_counts
from app.models.prerequisite import MilestoneDefinition, UserFilter

router = APIRouter(
    prefix="/api/v1/schedular/dashboard",
    tags=["dashboard"],
)


def _get_skipped_keys(config_db: Session) -> set[str]:
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


def _get_gate_checks(config_db: Session, user_id: str | None):
    """Load gate-check filters (plan_type, dev_initiatives) from saved user filters."""
    if not user_id:
        return None, None
    saved = config_db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
    if not saved:
        return None, None
    plan_type_include = None
    if saved.plan_type_include:
        try:
            plan_type_include = json.loads(saved.plan_type_include)
        except (json.JSONDecodeError, TypeError):
            pass
    return plan_type_include, saved.regional_dev_initiatives


@router.get("/sla-default-summary")
def dashboard_summary(
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual' (backward from CX start)"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    tab: str = Query("construction", description="AHLOA tab: 'construction' or 'survey' (ignored for macro)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Dashboard status counts. Supports project_type=ahloa with tab=construction|survey.
    """
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    user_skips = None
    if project_type == "ahloa" and user_id:
        from app.models.ahloa import AhloaUserSkippedPrerequisite
        rows = config_db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id
        ).all()
        user_skips = [(r.milestone_key, r.market) for r in rows]

    return get_dashboard_summary(
        db,
        config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_ed_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        status=status,
        user_id=user_id,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
        project_type=project_type,
        tab=tab,
        user_skips=user_skips,
    )


@router.get("/sla-history-summary")
def sla_dashboard_summary(
    date_from: str = Query(..., description="SLA history date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="SLA history date range end (YYYY-MM-DD)"),
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual' (backward from CX start)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Dashboard summary using SLA history (median completion days) for a date range.
    Uses the same filters as the gantt chart.

    Response:
      - sla_type: "history_median"
      - date_from, date_to: the date range used
      - sla_milestones: per-milestone median completion days + sample counts
      - dashboard_status, on_track_pct, total_sites, on_track_sites,
        in_progress_sites, critical_sites, blocked_sites
      - excluded_crew_shortage_sites, excluded_pace_constraint_sites
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    # Compute SLA history using median — with user filters applied
    from app.services.sla_history import compute_history_expected_days

    history_results = compute_history_expected_days(
        db, config_db, df, dt, use_median=True,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        view_type=view_type,
    )

    # Build overrides dict from median history
    history_overrides = {}
    for item in history_results:
        if item["history_expected_days"] is not None:
            history_overrides[item["milestone_key"]] = item["history_expected_days"]

    # Save per-user history expected days
    if user_id:
        save_user_history_expected_days(config_db, user_id, history_results, df, dt, view_type=view_type)

    # Get dashboard summary using history-based SLA overrides and gantt filters
    summary = get_dashboard_summary(
        db,
        config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=history_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        status=status,
        user_id=user_id,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return {
        "sla_type": "history_median",
        "date_from": date_from,
        "date_to": date_to,
        "sla_milestones": history_results,
        **summary,
    }


@router.get("/weekly-status-sla-default")
def weekly_status_user_override(
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID — uses user's SLA overrides if available"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual' (backward from CX start)"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    tab: str = Query("construction", description="AHLOA tab: 'construction' or 'survey' (ignored for macro)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Week-wise status counts using default/user override SLA.
    Supports project_type=ahloa with tab=construction|survey.
    """
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    user_skips = None
    if project_type == "ahloa" and user_id:
        from app.models.ahloa import AhloaUserSkippedPrerequisite
        rows = config_db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id
        ).all()
        user_skips = [(r.milestone_key, r.market) for r in rows]

    weeks = get_weekly_status_counts(
        db,
        config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_ed_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        status=status,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
        project_type=project_type,
        tab=tab,
        user_skips=user_skips,
    )

    return {"sla_type": "user_override" if user_id else "default", "weeks": weeks}


@router.get("/weekly-status-sla-history")
def weekly_status_history(
    date_from: str = Query(..., description="History date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="History date range end (YYYY-MM-DD)"),
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID — uses history-based SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual' (backward from CX start)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Week-wise status counts using SLA history-based overrides.

    Computes expected_days from historical actual dates within [date_from, date_to],
    then groups sites by ISO week/year based on forecasted_cx_start_date.
    Returns status counts per week. Supports all gantt-chart filters.
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    from app.services.sla_history import compute_history_expected_days

    history_results = compute_history_expected_days(
        db, config_db, df, dt,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        view_type=view_type,
    )

    history_overrides = {}
    for item in history_results:
        computed = item["history_expected_days"]
        history_overrides[item["milestone_key"]] = computed if computed is not None else 0

    # Save per-user history expected days
    if user_id:
        save_user_history_expected_days(config_db, user_id, history_results, df, dt, view_type=view_type)

    weeks = get_weekly_status_counts(
        db,
        config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=history_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        status=status,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return {
        "sla_type": "history",
        "date_from": date_from,
        "date_to": date_to,
        "weeks": weeks,
    }
