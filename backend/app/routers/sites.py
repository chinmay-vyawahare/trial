import json
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter, MilestoneDefinition
from app.services.gantt import get_all_sites_gantt, get_dashboard_summary
from app.services.gantt.milestones import get_user_expected_days_overrides

router = APIRouter(prefix="/api/v1/schedular/gantt-charts", tags=["gantt-charts"])


# ----------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------

def _get_user_filters(db: Session, user_id: str) -> UserFilter | None:
    """Return saved filters for a user, or None."""
    return db.query(UserFilter).filter(UserFilter.user_id == user_id).first()


def _save_user_filters(
    db: Session,
    user_id: str,
    region: str | None,
    market: str | None,
    site_id: str | None,
    vendor: str | None,
    area: str | None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
):
    """Upsert filter preferences for a user."""
    pti_json = json.dumps(plan_type_include) if plan_type_include else None

    existing = _get_user_filters(db, user_id)

    if existing:
        existing.region = region
        existing.market = market
        existing.vendor = vendor
        existing.site_id = site_id
        existing.area = area
        existing.plan_type_include = pti_json
        existing.regional_dev_initiatives = regional_dev_initiatives
    else:
        db.add(UserFilter(
            user_id=user_id,
            region=region,
            market=market,
            vendor=vendor,
            site_id=site_id,
            area=area,
            plan_type_include=pti_json,
            regional_dev_initiatives=regional_dev_initiatives,
        ))

    db.commit()


def _resolve_filters(
    config_db: Session,
    user_id: str | None,
    region: str | None,
    market: str | None,
    site_id: str | None,
    vendor: str | None,
    area: str | None,
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
        region = region if region is not None else saved.region
        market = market if market is not None else saved.market
        site_id = site_id if site_id is not None else saved.site_id
        vendor = vendor if vendor is not None else saved.vendor
        area = area if area is not None else saved.area

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


def _get_skipped_keys(config_db: Session) -> set[str]:
    """Return the set of globally skipped milestone keys (admin-set)."""
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


# ----------------------------------------------------------------
# Gantt chart endpoints
# ----------------------------------------------------------------

@router.get("")
def list_sites(
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area (m_area column)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    limit: int = Query(None, description="Limit the number of results"),
    offset: int = Query(None, description="Offset the results"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints — marks excess sites as excluded"),
    pace_constraint_id: int = Query(None, description="Apply a specific pace constraint by ID — marks excess sites as excluded"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit must be a positive integer.")
    if offset is not None and offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0.")

    region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, site_id, vendor, area
    )
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id else {}

    sites, total_count, count = get_all_sites_gantt(
        db,
        config_db,
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
        user_expected_days_overrides=user_ed_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_id=pace_constraint_id,
    )
    return {
        "count": count,
        "sites": sites,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_count": total_count,
        },
    }


@router.get("/dashboard")
def dashboard(
    user_id: str = Query(..., description="User ID — filters are loaded from saved preferences"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Dashboard summary. All filters are read from the user's saved
    UserFilter row — no manual filter params needed.
    """
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    saved = _get_user_filters(config_db, user_id)

    region = saved.region if saved else None
    market = saved.market if saved else None
    vendor = saved.vendor if saved else None
    area = saved.area if saved else None

    plan_type_include = None
    regional_dev_initiatives = None
    if saved:
        if saved.plan_type_include:
            try:
                plan_type_include = json.loads(saved.plan_type_include)
            except (json.JSONDecodeError, TypeError):
                pass
        regional_dev_initiatives = saved.regional_dev_initiatives

    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id)

    return get_dashboard_summary(
        db,
        config_db,
        region=region,
        market=market,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_ed_overrides,
    )
