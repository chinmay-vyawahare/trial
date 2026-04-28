"""
AHLOA Gantt Chart Router

Separate API endpoints for AHLOA project type.
Does not touch any existing NTM/MACRO code.
"""

import json
import logging
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter
from app.services.ahloa.gantt_ahloa_construction import get_ahloa_gantt
from app.services.ahloa.gantt_ahloa_scope import get_ahloa_gantt_scope

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/ahloa",
    tags=["ahloa"],
)


# ----------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------

def _get_user_filters(db: Session, user_id: str) -> UserFilter | None:
    """Return saved filters for a user, or None."""
    return db.query(UserFilter).filter(UserFilter.user_id == user_id).first()


def _save_user_filters(
    db: Session,
    user_id: str,
    region: list[str] | None,
    market: list[str] | None,
    site_id: str | None,
    vendor: str | None,
    area: list[str] | None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
):
    """Upsert filter preferences for a user."""
    pti_json = json.dumps(plan_type_include) if plan_type_include else None
    region_json = json.dumps(region) if region else None
    market_json = json.dumps(market) if market else None
    area_json = json.dumps(area) if area else None

    existing = _get_user_filters(db, user_id)

    if existing:
        existing.region = region_json
        existing.market = market_json
        existing.vendor = vendor
        existing.site_id = site_id
        existing.area = area_json
        existing.plan_type_include = pti_json
        existing.regional_dev_initiatives = regional_dev_initiatives
    else:
        db.add(UserFilter(
            user_id=user_id,
            region=region_json,
            market=market_json,
            vendor=vendor,
            site_id=site_id,
            area=area_json,
            plan_type_include=pti_json,
            regional_dev_initiatives=regional_dev_initiatives,
        ))

    db.commit()


def _resolve_filters(
    config_db: Session,
    user_id: str | None,
    region: list[str] | None,
    market: list[str] | None,
    site_id: str | None,
    vendor: str | None,
    area: list[str] | None,
):
    """
    Merge explicit query-param filters with the user's saved filters.

    Explicit params always win for the normal filters.
    Gate checks (plan_type_include, regional_dev_initiatives) are always
    read from the saved UserFilter row when a user_id is provided.
    After merging, the effective filters are persisted back.
    """
    plan_type_include = None
    regional_dev_initiatives = None

    if not user_id:
        return region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives

    saved = _get_user_filters(config_db, user_id)

    if saved:
        # Gate checks always come from the DB
        if saved.plan_type_include:
            try:
                plan_type_include = json.loads(saved.plan_type_include)
            except (json.JSONDecodeError, TypeError):
                pass
        regional_dev_initiatives = saved.regional_dev_initiatives

    # Persist the effective filters back (upsert)
    _save_user_filters(
        config_db, user_id, region, market, site_id, vendor, area,
        plan_type_include, regional_dev_initiatives,
    )

    return region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives


def _load_user_skips(config_db: Session, user_id: str | None) -> list[tuple[str, str | None, str | None]]:
    """Load AHLOA per-user skips as [(milestone_key, market|None, area|None)].

    At most ONE of market/area is set per row (router enforces this).
    Both NULL = global skip across all markets for this user.
    """
    if not user_id:
        return []
    from app.models.ahloa import AhloaUserSkippedPrerequisite
    rows = (
        config_db.query(AhloaUserSkippedPrerequisite)
        .filter(AhloaUserSkippedPrerequisite.user_id == user_id)
        .all()
    )
    return [(r.milestone_key, r.market, r.area) for r in rows]


# ----------------------------------------------------------------
# Gantt chart endpoints
# ----------------------------------------------------------------

@router.get("/gantt-chart-construction")
def ahloa_construction_gantt(
    region: list[str] = Query(None),
    market: list[str] = Query(None),
    site_id: str = None,
    vendor: str = None,
    area: list[str] = Query(None),
    user_id: str = Query(None, description="User ID for saved filters"),
    limit: int = None,
    offset: int = None,
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    strict_pace_apply: bool = Query(False, description="Strict pace: exclude overflow sites instead of pushing to next week"),
    status: str = Query(None, description="Filter by overall_status: ON TRACK, IN PROGRESS, CRITICAL"),
    start_date: date = Query(None, description="Filter sites where CX start date >= this date"),
    end_date: date = Query(None, description="Filter sites where CX start date <= this date"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    AHLOA gantt chart — site-wise milestone-wise data.

    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days
    Each milestone status is based on actual vs expected (CX Start + offset).
    """
    region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, site_id, vendor, area,
    )

    user_skips = _load_user_skips(config_db, user_id)

    sites, total_count, count = get_ahloa_gantt(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        strict_pace_apply=strict_pace_apply,
        status=status,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        user_skips=user_skips,
    )

    # Post-filter by overall_status if requested
    if status:
        status_upper = status.upper()
        sites = [
            s for s in sites
            if s.get("overall_status", "").upper() == status_upper
        ]
        count = len(sites)

    return {
        "total_count": total_count,
        "count": count,
        "sites": sites,
    }


@router.get("/gantt-chart-scope")
def ahloa_scope_gantt(
    region: list[str] = Query(None),
    market: list[str] = Query(None),
    site_id: str = None,
    vendor: str = None,
    area: list[str] = Query(None),
    user_id: str = Query(None, description="User ID for saved filters"),
    limit: int = None,
    offset: int = None,
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    status: str = Query(None, description="Filter by overall_status: ON TRACK, IN PROGRESS, CRITICAL"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    AHLOA gantt chart (scope) — site-wise milestone-wise data.

    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days
    Each milestone status is based on actual vs expected (CX Start + offset).
    """
    user_skips = _load_user_skips(config_db, user_id)

    sites, total_count, count = get_ahloa_gantt_scope(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        limit=limit,
        offset=offset,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        user_skips=user_skips,
    )

    # Post-filter by overall_status if requested
    if status:
        status_upper = status.upper()
        sites = [
            s for s in sites
            if s.get("overall_status", "").upper() == status_upper
        ]
        count = len(sites)

    return {
        "total_count": total_count,
        "count": count,
        "sites": sites,
    }
