"""
SLA History endpoints.

- GET  /sla-history/gantt-charts  — gantt chart using history-based SLA (computes + saves + returns)
- POST /sla-history/reset         — clear all history_expected_days values
"""

import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db, get_config_db
from app.models.prerequisite import MilestoneDefinition, UserFilter
from app.services.gantt import get_history_gantt

router = APIRouter(
    prefix="/api/v1/schedular/sla-history",
    tags=["gantt-chart-sla-history"],
)


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _resolve_user_filters(config_db: Session, user_id: str | None):
    """Load saved user filters and gate checks."""
    if not user_id:
        return None, None, None, None, None, None, None

    saved = config_db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
    if not saved:
        return None, None, None, None, None, None, None

    plan_type_include = None
    if saved.plan_type_include:
        try:
            plan_type_include = json.loads(saved.plan_type_include)
        except (json.JSONDecodeError, TypeError):
            pass

    return (
        saved.region, saved.market, saved.site_id,
        saved.vendor, saved.area,
        plan_type_include, saved.regional_dev_initiatives,
    )


def _get_skipped_keys(config_db: Session) -> set[str]:
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@router.get("/gantt-charts")
def history_gantt_charts(
    date_from: str = Query(..., description="History date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="History date range end (YYYY-MM-DD)"),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID for saved filters"),
    limit: int = Query(None, description="Limit results"),
    offset: int = Query(None, description="Offset results"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID — marks excess sites as excluded"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Gantt chart using history-based SLA.

    Computes expected_days from historical actual dates within [date_from, date_to],
    saves them into milestone_definitions.history_expected_days,
    then returns the gantt chart using those values.
    """
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit must be a positive integer.")
    if offset is not None and offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0.")

    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    # Merge explicit filters with saved user filters
    saved_region, saved_market, saved_site_id, saved_vendor, saved_area, plan_type_include, regional_dev_initiatives = (
        _resolve_user_filters(config_db, user_id)
    )
    region = region or saved_region
    market = market or saved_market
    site_id = site_id or saved_site_id
    vendor = vendor or saved_vendor
    area = area or saved_area

    skipped_keys = _get_skipped_keys(config_db)

    sites, total_count, count, sla_last_updated = get_history_gantt(
        db=db,
        config_db=config_db,
        date_from=df,
        date_to=dt,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_id=pace_constraint_id,
    )
    return {
        "sla_type": "history",
        "date_from": date_from,
        "date_to": date_to,
        "sla_last_updated": sla_last_updated,
        "count": count,
        "sites": sites,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_count": total_count,
        },
    }


@router.post("/reset")
def reset_sla_to_default(
    config_db: Session = Depends(get_config_db),
):
    """
    Clear all history_expected_days from milestone_definitions,
    reverting to default expected_days.
    """
    updated = (
        config_db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.history_expected_days.isnot(None))
        .update({MilestoneDefinition.history_expected_days: None})
    )
    config_db.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail="No history SLA values found to reset")
    return {"detail": f"Reset history_expected_days for {updated} milestones"}
