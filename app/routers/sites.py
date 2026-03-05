import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter, UserSkippedPrerequisite
from app.services.gantt import get_all_sites_gantt, get_dashboard_summary

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


def _get_skipped_keys(config_db: Session, user_id: str | None) -> set[str]:
    """Return the set of milestone keys the user has chosen to skip."""
    if not user_id:
        return set()
    rows = (
        config_db.query(UserSkippedPrerequisite.milestone_key)
        .filter(UserSkippedPrerequisite.user_id == user_id)
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
    user_id: str = Query(None, description="User ID for saved filters & skipped prerequisites"),
    limit: int = Query(None, description="Limit the number of results"),
    offset: int = Query(None, description="Offset the results"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, site_id, vendor, area
    )
    skipped_keys = _get_skipped_keys(config_db, user_id)

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
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: str = Query(None, description="Filter by area (m_area column)"),
    user_id: str = Query(None, description="User ID for saved filters & skipped prerequisites"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    region, market, _, vendor, area, plan_type_include, regional_dev_initiatives = _resolve_filters(
        config_db, user_id, region, market, None, vendor, area
    )
    skipped_keys = _get_skipped_keys(config_db, user_id)

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
    )
