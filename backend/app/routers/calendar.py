import json
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter, MilestoneDefinition
from app.services.calendar import get_calendar_sites, get_calendar_history_sites
from app.services.gantt.milestones import get_user_expected_days_overrides

router = APIRouter(
    prefix="/api/v1/schedular/calendar",
    tags=["calendar"],
)


# ----------------------------------------------------------------
# Internal helpers (same pattern as sites router)
# ----------------------------------------------------------------

def _get_user_filters(db: Session, user_id: str) -> UserFilter | None:
    return db.query(UserFilter).filter(UserFilter.user_id == user_id).first()


def _resolve_filters(
    config_db: Session,
    user_id: str | None,
    region: str | None,
    market: str | None,
    site_id: str | None,
    vendor: str | None,
    area: str | None,
):
    plan_type_include = None
    regional_dev_initiatives = None

    if not user_id:
        return region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives

    saved = _get_user_filters(config_db, user_id)

    if saved:
        if saved.plan_type_include:
            try:
                plan_type_include = json.loads(saved.plan_type_include)
            except (json.JSONDecodeError, TypeError):
                pass
        regional_dev_initiatives = saved.regional_dev_initiatives

    return region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives


def _get_skipped_keys(config_db: Session) -> set[str]:
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


# ----------------------------------------------------------------
# Calendar endpoints
# ----------------------------------------------------------------

@router.get("")
def get_calendar(
    start_date: date = Query(..., description="Start date for calendar range (YYYY-MM-DD). Must be less than or equal to end_date."),
    end_date: date = Query(..., description="End date for calendar range (YYYY-MM-DD). Must be greater than or equal to start_date."),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area (m_area column)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status (ON TRACK, IN PROGRESS, CRITICAL, Blocked, etc.)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Calendar view — returns gantt chart sites whose forecasted_cx_start_date
    falls within the given [start_date, end_date] range.
    """
    # Validations
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be less than or equal to end_date.",
        )

    region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, site_id, vendor, area
    )
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id else {}

    sites = get_calendar_sites(
        db=db,
        config_db=config_db,
        start_date=start_date,
        end_date=end_date,
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

    return {
        "sla_type": "default",
        "start_date": str(start_date),
        "end_date": str(end_date),
        "count": len(sites),
        "sites": sites,
    }


@router.get("/history")
def get_calendar_history(
    start_date: date = Query(..., description="Calendar range start (YYYY-MM-DD) — filters forecasted_cx_start_date."),
    end_date: date = Query(..., description="Calendar range end (YYYY-MM-DD) — filters forecasted_cx_start_date."),
    sla_date_from: date = Query(..., description="SLA history date range start (YYYY-MM-DD) — used to compute history-based expected_days."),
    sla_date_to: date = Query(..., description="SLA history date range end (YYYY-MM-DD) — used to compute history-based expected_days."),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area (m_area column)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID"),
    status: str = Query(None, description="Filter by overall_status (ON TRACK, IN PROGRESS, CRITICAL, Blocked, etc.)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Calendar view using history-based SLA — computes expected_days from historical
    actual dates within [sla_date_from, sla_date_to], then returns only sites whose
    forecasted_cx_start_date falls within [start_date, end_date].
    """
    # Validations
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be less than or equal to end_date.",
        )
    if sla_date_from > sla_date_to:
        raise HTTPException(
            status_code=400,
            detail="sla_date_from must be less than or equal to sla_date_to.",
        )

    region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, site_id, vendor, area
    )
    skipped_keys = _get_skipped_keys(config_db)

    sites, sla_last_updated = get_calendar_history_sites(
        db=db,
        config_db=config_db,
        start_date=start_date,
        end_date=end_date,
        sla_date_from=sla_date_from,
        sla_date_to=sla_date_to,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_id=pace_constraint_id,
        status=status,
    )

    return {
        "sla_type": "history",
        "start_date": str(start_date),
        "end_date": str(end_date),
        "sla_date_from": str(sla_date_from),
        "sla_date_to": str(sla_date_to),
        "sla_last_updated": sla_last_updated,
        "count": len(sites),
        "sites": sites,
    }
