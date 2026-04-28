"""
Analytics endpoints — pending milestone distribution.

GET /analytics/pending-milestones/auto        — using default/user-override SLA
GET /analytics/pending-milestones/sla-history — using SLA history (median)

All endpoints accept optional filter_date_from / filter_date_to to restrict
results to sites whose forecasted_cx_start_date falls within the given range.
"""

import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db, get_config_db
from app.models.prerequisite import MilestoneDefinition, UserFilter
from app.services.gantt.milestones import get_user_expected_days_overrides
from app.services.analytics import (
    get_pending_milestones_auto,
    get_pending_milestones_history,
    get_pending_by_milestone_auto,
    get_pending_by_milestone_history,
    drilldown_sites_auto,
    drilldown_sites_history,
)

router = APIRouter(
    prefix="/api/v1/schedular/analytics",
    tags=["analytics"],
)


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _get_skipped_keys(config_db: Session) -> set[str]:
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


def _get_gate_checks(config_db: Session, user_id: str | None):
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


def _parse_optional_date(raw: str | None, label: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} format. Use YYYY-MM-DD.")


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@router.get("/pending-milestones/auto")
def pending_milestones_auto(
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    tab: str = Query("construction", description="AHLOA tab: 'construction' or 'survey' (ignored for macro)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Pending milestone distribution using default/user-override SLA.
    Supports project_type=ahloa with tab=construction|survey.
    """
    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    user_skips = None
    if project_type == "ahloa" and user_id:
        from app.models.ahloa import AhloaUserSkippedPrerequisite
        rows = config_db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id
        ).all()
        user_skips = [(r.milestone_key, r.market, r.area) for r in rows]

    data = get_pending_milestones_auto(
        db, config_db,
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
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
        project_type=project_type,
        tab=tab,
        user_skips=user_skips,
    )

    return {
        "sla_type": "user_override" if user_id else "default",
        "total_sites": data["total_sites"],
        "blocked_sites": data["blocked_sites"],
        "pending_milestones": data["buckets"],
    }


@router.get("/pending-milestones/sla-history")
def pending_milestones_sla_history(
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
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Pending milestone distribution using SLA history (median completion days).
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    data = get_pending_milestones_history(
        db, config_db,
        date_from=df,
        date_to=dt,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return {
        "sla_type": "history_median",
        "date_from": date_from,
        "date_to": date_to,
        "total_sites": data["total_sites"],
        "blocked_sites": data["blocked_sites"],
        "pending_milestones": data["buckets"],
    }


@router.get("/pending-by-milestone/auto")
def pending_by_milestone_auto(
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    tab: str = Query("construction", description="AHLOA tab: 'construction' or 'survey' (ignored for macro)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """Per-milestone pending site count. Supports project_type=ahloa with tab."""
    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    user_skips = None
    if project_type == "ahloa" and user_id:
        from app.models.ahloa import AhloaUserSkippedPrerequisite
        rows = config_db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id
        ).all()
        user_skips = [(r.milestone_key, r.market, r.area) for r in rows]

    data = get_pending_by_milestone_auto(
        db, config_db,
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
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
        project_type=project_type,
        tab=tab,
        user_skips=user_skips,
    )

    return {
        "sla_type": "user_override" if user_id else "default",
        "total_sites": data["total_sites"],
        "blocked_sites": data["blocked_sites"],
        "milestones": data["milestones"],
    }


@router.get("/pending-by-milestone/sla-history")
def pending_by_milestone_sla_history(
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
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Per-milestone pending site count using SLA history (median completion days).
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    data = get_pending_by_milestone_history(
        db, config_db,
        date_from=df,
        date_to=dt,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return {
        "sla_type": "history_median",
        "date_from": date_from,
        "date_to": date_to,
        "total_sites": data["total_sites"],
        "blocked_sites": data["blocked_sites"],
        "milestones": data["milestones"],
    }


@router.get("/drilldown/auto")
def drilldown_auto(
    drilldown_type: str = Query(..., description="Type of drilldown: 'pending_count' or 'milestone_key'"),
    pending_count: int = Query(None, description="For pending_count drilldown: exact number of pending milestones"),
    milestone_key: str = Query(None, description="For milestone_key drilldown: the milestone key to filter by"),
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    tab: str = Query("construction", description="AHLOA tab: 'construction' or 'survey' (ignored for macro)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """Drilldown into analytics charts. Supports project_type=ahloa with tab."""
    if drilldown_type not in ("pending_count", "milestone_key"):
        raise HTTPException(status_code=400, detail="drilldown_type must be 'pending_count' or 'milestone_key'")
    if drilldown_type == "pending_count" and pending_count is None:
        raise HTTPException(status_code=400, detail="pending_count is required for pending_count drilldown")
    if drilldown_type == "milestone_key" and not milestone_key:
        raise HTTPException(status_code=400, detail="milestone_key is required for milestone_key drilldown")

    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    user_skips = None
    if project_type == "ahloa" and user_id:
        from app.models.ahloa import AhloaUserSkippedPrerequisite
        rows = config_db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id
        ).all()
        user_skips = [(r.milestone_key, r.market, r.area) for r in rows]

    sites, blocked = drilldown_sites_auto(
        db, config_db,
        drilldown_type=drilldown_type,
        pending_count=pending_count,
        milestone_key=milestone_key,
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
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
        project_type=project_type,
        tab=tab,
        user_skips=user_skips,
    )

    return {
        "drilldown_type": drilldown_type,
        "pending_count": pending_count,
        "milestone_key": milestone_key,
        "count": len(sites),
        "blocked_sites": blocked,
        "sites": sites,
    }


@router.get("/drilldown/sla-history")
def drilldown_sla_history(
    date_from: str = Query(..., description="SLA history date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="SLA history date range end (YYYY-MM-DD)"),
    drilldown_type: str = Query(..., description="Type of drilldown: 'pending_count' or 'milestone_key'"),
    pending_count: int = Query(None, description="For pending_count drilldown: exact number of pending milestones"),
    milestone_key: str = Query(None, description="For milestone_key drilldown: the milestone key to filter by"),
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    filter_date_from: str = Query(None, description="Only include sites with forecasted CX start >= this date (YYYY-MM-DD)"),
    filter_date_to: str = Query(None, description="Only include sites with forecasted CX start <= this date (YYYY-MM-DD)"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual'"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Drilldown into SLA history analytics charts — returns full gantt site data for the clicked bar.
    """
    if drilldown_type not in ("pending_count", "milestone_key"):
        raise HTTPException(status_code=400, detail="drilldown_type must be 'pending_count' or 'milestone_key'")
    if drilldown_type == "pending_count" and pending_count is None:
        raise HTTPException(status_code=400, detail="pending_count is required for pending_count drilldown")
    if drilldown_type == "milestone_key" and not milestone_key:
        raise HTTPException(status_code=400, detail="milestone_key is required for milestone_key drilldown")

    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    fd_from = _parse_optional_date(filter_date_from, "filter_date_from")
    fd_to = _parse_optional_date(filter_date_to, "filter_date_to")

    skipped_keys = _get_skipped_keys(config_db)
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    sites, blocked = drilldown_sites_history(
        db, config_db,
        date_from=df,
        date_to=dt,
        drilldown_type=drilldown_type,
        pending_count=pending_count,
        milestone_key=milestone_key,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=fd_from,
        filter_date_to=fd_to,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return {
        "drilldown_type": drilldown_type,
        "pending_count": pending_count,
        "milestone_key": milestone_key,
        "date_from": date_from,
        "date_to": date_to,
        "count": len(sites),
        "blocked_sites": blocked,
        "sites": sites,
    }
