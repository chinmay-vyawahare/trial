"""
CX Actual Construction Summary router.

GET /api/v1/schedular/cx-actual-summary  — week-wise site counts based on
    pj_a_4225_construction_start_finish (actual construction start date).
    Defaults to current month start → today.
"""

import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter
from app.services.cx_actual_summary import get_cx_actual_weekly_summary

router = APIRouter(
    prefix="/api/v1/schedular/cx-actual-summary",
    tags=["cx-actual-summary"],
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
def cx_actual_weekly_summary(
    start_date: str = Query(None, description="Start date (YYYY-MM-DD) — defaults to 1st of current month"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD) — defaults to today"),
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
    Week-wise site summary based on actual construction start date
    (pj_a_4225_construction_start_finish IS NOT NULL).

    Default range: 1st of current month → today.
    Same filters as the CX forecast endpoint.
    """
    plan_type_include, regional_dev_initiatives = _get_gate_checks(config_db, user_id)

    weeks, applied_start, applied_end = get_cx_actual_weekly_summary(
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
        "start_date": applied_start,
        "end_date": applied_end,
        "weeks": weeks,
    }
