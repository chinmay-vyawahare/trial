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
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Return dashboard status counts using the same filters as the gantt chart.

    Response:
      - dashboard_status: overall status label
      - on_track_pct: percentage of on-track sites
      - total_sites, on_track_sites, in_progress_sites, critical_sites, blocked_sites
      - excluded_crew_shortage_sites, excluded_pace_constraint_sites
    """
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

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
        pace_constraint_id=pace_constraint_id,
        status=status,
    )


@router.get("/sla-history-summary")
def sla_dashboard_summary(
    date_from: str = Query(..., description="SLA history date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="SLA history date range end (YYYY-MM-DD)"),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID for saved filters"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
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

    # Compute SLA history using median
    from app.services.sla_history import compute_history_expected_days

    history_results = compute_history_expected_days(db, config_db, df, dt, use_median=True)

    # Build overrides dict from median history
    history_overrides = {}
    for item in history_results:
        if item["history_expected_days"] is not None:
            history_overrides[item["milestone_key"]] = item["history_expected_days"]

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

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
        pace_constraint_id=pace_constraint_id,
        status=status,
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
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID — uses user's SLA overrides if available"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Week-wise status counts using default/user override SLA.

    Groups sites by ISO week/year based on forecasted_cx_start_date.
    Returns status counts per week. Supports all gantt-chart filters.
    If user_id is provided, uses that user's SLA overrides (expected_days).
    """
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

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
        pace_constraint_id=pace_constraint_id,
        status=status,
    )

    return {"sla_type": "user_override" if user_id else "default", "weeks": weeks}


@router.get("/weekly-status-sla-history")
def weekly_status_history(
    date_from: str = Query(..., description="History date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="History date range end (YYYY-MM-DD)"),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID — uses history-based SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
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

    from app.services.sla_history import compute_history_expected_days

    history_results = compute_history_expected_days(db, config_db, df, dt)

    history_overrides = {}
    for item in history_results:
        computed = item["history_expected_days"]
        history_overrides[item["milestone_key"]] = computed if computed is not None else 0

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

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
        pace_constraint_id=pace_constraint_id,
        status=status,
    )

    return {
        "sla_type": "history",
        "date_from": date_from,
        "date_to": date_to,
        "weeks": weeks,
    }
