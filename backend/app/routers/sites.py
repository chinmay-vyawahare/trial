import json
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter, MilestoneDefinition
from app.services.gantt import get_all_sites_gantt, get_dashboard_summary
from app.services.gantt.milestones import get_user_expected_days_overrides
from app.services.ahloa.gantt_ahloa_construction import get_ahloa_gantt

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
    # Store list filters as JSON, single values as-is
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
        # NOTE: Do NOT merge saved geographic filters (region, market, etc.)
        # into the query. The frontend already loads saved filters into the
        # sidebar UI via handleUserIdApply → getUserFilters. Merging here
        # causes stale saved filters to silently narrow results when the user
        # has intentionally left a filter empty (e.g. when using pace constraints).
        # Only gate-check filters (plan_type, dev_initiatives) are DB-only.

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
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID for saved filters"),
    limit: int = Query(None, description="Limit the number of results"),
    offset: int = Query(None, description="Offset the results"),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints — marks excess sites as excluded"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user — marks excess sites as excluded"),
    strict_pace_apply: bool = Query(False, description="When true, exclude excess sites without stretching to next week"),
    status: str = Query(None, description="Filter by overall_status. Possible values: ON TRACK, IN PROGRESS, CRITICAL, Blocked, Excluded - Crew Shortage, Excluded - Pace Constraint"),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
    project_type: str = Query("macro", description="Project type: 'macro' (default) or 'ahloa'"),
    view_type: str = Query("forecast", description="View type: 'forecast' (default) or 'actual' (backward from CX start)"),
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

    # --- AHLOA branch ---
    if project_type == "ahloa":
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
            status=status,
            user_id=user_id,
        )
    else:
        # --- Macro (default) branch ---
        skipped_keys = _get_skipped_keys(config_db)
        user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id and sla_type == "user_based" else {}
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
            pace_constraint_flag=pace_constraint_flag,
            user_id=user_id,
            strict_pace_apply=strict_pace_apply,
            view_type=view_type,
        )

    # Post-filter by overall_status or exclude_reason if requested
    if status:
        status_upper = status.upper()
        sites = [
            s for s in sites
            if s.get("overall_status", "").upper() == status_upper
            or (s.get("exclude_reason") or "").upper() == status_upper
        ]
        count = len(sites)

    return {
        "count": count,
        "sites": sites,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_count": total_count,
        },
    }
