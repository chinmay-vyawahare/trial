"""
CX Forecast Weekly Summary router.

GET /api/v1/schedular/cx-forecast-summary  — week-wise site counts based on
    pj_p_4225_construction_start_finish (planned construction start date).
"""

import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter
from app.services.cx_forecast_summary import get_cx_forecast_weekly_summary

router = APIRouter(
    prefix="/api/v1/schedular/cx-forecast-summary",
    tags=["cx-forecast-summary"],
)


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


@router.get("")
def cx_forecast_weekly_summary(
    start_date: str = Query(None, description="Start date filter (YYYY-MM-DD) — only sites with CX start >= this date"),
    end_date: str = Query(None, description="End date filter (YYYY-MM-DD) — only sites with CX start <= this date"),
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area"),
    user_id: str = Query(None, description="User ID for saved gate-check filters"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Week-wise site summary based on planned construction start date
    (pj_p_4225_construction_start_finish).

    Filters: region, market, area, site_id, vendor, start_date, end_date.
    Gate checks (smp_name=NTM, non-empty construction_gc,
    pj_a_4225_construction_start_finish IS NULL) are always applied.
    User's saved plan_type_include and regional_dev_initiatives are applied
    when user_id is provided.

    Response: list of weeks, each with total count and site details.
    """
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    weeks = get_cx_forecast_weekly_summary(
        db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "total_sites": sum(w["total"] for w in weeks),
        "total_weeks": len(weeks),
        "weeks": weeks,
    }
