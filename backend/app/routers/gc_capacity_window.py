"""
Per-user GC vendor capacity windows CRUD.

Each row defines a recurring window [start_date, end_date) and a max_sites cap.
The same window length repeats forward forever (e.g. start=12-Mar, end=17-Mar
→ 5-day windows: [12,17), [17,22), [22,27), ...).

Consumed by `_apply_vendor_capacity` whenever consider_vendor_capacity=True
AND a user_id is present — no separate flag is needed.

- POST   /gc-capacity-windows                       — create
- GET    /gc-capacity-windows?user_id=...           — list (optional ?project_type)
- PUT    /gc-capacity-windows/{id}?user_id=...      — update
- DELETE /gc-capacity-windows/{id}?user_id=...      — delete
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_config_db, get_db
from app.models.prerequisite import GcCapacityWindow
from app.schemas.gantt import (
    GcCapacityWindowCreate,
    GcCapacityWindowOut,
    GcCapacityWindowUpdate,
)
from app.services.gantt.queries import get_geo_hierarchy


router = APIRouter(
    prefix="/api/v1/schedular/gc-capacity-windows",
    tags=["gc-capacity-windows"],
)


def _normalize_project_type(value: str | None) -> str:
    pt = (value or "macro").strip().lower()
    if pt not in ("macro", "ahloa"):
        raise HTTPException(
            status_code=400,
            detail="project_type must be 'macro' or 'ahloa'.",
        )
    return pt


def _validate_single_geo_level(region, area, market):
    filled = sum(1 for v in (region, area, market) if v and v.strip())
    if filled > 1:
        raise HTTPException(
            status_code=400,
            detail="Only one geo level (region, area, or market) can be set per window.",
        )


def _validate_geo_hierarchy(
    staging_db: Session,
    config_db: Session,
    user_id: str,
    project_type: str,
    vendor_name: str | None,
    body_region: str | None,
    body_area: str | None,
    body_market: str | None,
    exclude_id: int | None = None,
):
    """
    Reject overlapping windows along the region → area → market hierarchy,
    scoped to the same (user_id, project_type, vendor_name). Two windows on the
    same geo are allowed if they target different vendors (or one vendor-specific
    + one vendor-wide can coexist if you want — see below).

    Vendor matching: case-insensitive equality, with NULL == NULL. Different
    vendor strings under the same geo are NOT treated as conflicts so you can
    have one rule per vendor in the same geo.
    """
    geo = get_geo_hierarchy(staging_db, project_type=project_type)

    # Multimaps — one area/market can roll up to multiple regions/areas in
    # this dataset (e.g. area "IL" appears under both "Central" and "East").
    # A single-key dict would silently lose parents and skip valid conflicts.
    from collections import defaultdict
    market_to_areas: dict[str, set[str]] = defaultdict(set)
    market_to_regions: dict[str, set[str]] = defaultdict(set)
    area_to_regions: dict[str, set[str]] = defaultdict(set)
    for row in geo:
        r = row["region"].strip().lower()
        a = row["area"].strip().lower()
        m = row["market"].strip().lower()
        market_to_areas[m].add(a)
        market_to_regions[m].add(r)
        area_to_regions[a].add(r)

    new_vendor = (vendor_name or "").strip().lower()
    existing = (
        config_db.query(GcCapacityWindow)
        .filter(
            GcCapacityWindow.user_id == user_id,
            GcCapacityWindow.project_type == project_type,
        )
        .all()
    )
    if exclude_id:
        existing = [w for w in existing if w.id != exclude_id]
    # Only conflict against rows with the SAME vendor (NULL matches NULL)
    existing = [w for w in existing if (w.vendor_name or "").strip().lower() == new_vendor]

    new_region = (body_region or "").strip().lower()
    new_area = (body_area or "").strip().lower()
    new_market = (body_market or "").strip().lower()

    vendor_label = vendor_name or "(any vendor)"

    for c in existing:
        c_region = (c.region or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_market = (c.market or "").strip().lower()

        if new_region:
            if c_region == new_region:
                raise HTTPException(status_code=400, detail=f"A window for region '{body_region}' already exists for vendor {vendor_label}.")
            if c_area and new_region in area_to_regions.get(c_area, set()):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add region '{body_region}' — existing window for vendor {vendor_label} covers area '{c.area}' which belongs to this region.",
                )
            if c_market and new_region in market_to_regions.get(c_market, set()):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add region '{body_region}' — existing window for vendor {vendor_label} covers market '{c.market}' which belongs to this region.",
                )

        elif new_area:
            if c_area == new_area:
                raise HTTPException(status_code=400, detail=f"A window for area '{body_area}' already exists for vendor {vendor_label}.")
            parent_regions = area_to_regions.get(new_area, set())
            if c_region and c_region in parent_regions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add area '{body_area}' — existing window for vendor {vendor_label} covers region '{c.region}' which is a higher hierarchy.",
                )
            if c_market and new_area in market_to_areas.get(c_market, set()):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add area '{body_area}' — existing window for vendor {vendor_label} covers market '{c.market}' which belongs to this area.",
                )

        elif new_market:
            if c_market == new_market:
                raise HTTPException(status_code=400, detail=f"A window for market '{body_market}' already exists for vendor {vendor_label}.")
            parent_regions = market_to_regions.get(new_market, set())
            if c_region and c_region in parent_regions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add market '{body_market}' — existing window for vendor {vendor_label} covers region '{c.region}' which is a higher hierarchy.",
                )
            parent_areas = market_to_areas.get(new_market, set())
            if c_area and c_area in parent_areas:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add market '{body_market}' — existing window for vendor {vendor_label} covers area '{c.area}' which is a higher hierarchy.",
                )


def _parse_required_date(field: str, value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field} format. Use YYYY-MM-DD.",
        )


@router.get("", response_model=list[GcCapacityWindowOut])
def list_gc_capacity_windows(
    user_id: str = Query(..., description="User ID"),
    project_type: str | None = Query(
        None,
        description="Optional 'macro' or 'ahloa' filter. Omit to list across both.",
    ),
    db: Session = Depends(get_config_db),
):
    q = db.query(GcCapacityWindow).filter(GcCapacityWindow.user_id == user_id)
    if project_type is not None:
        q = q.filter(GcCapacityWindow.project_type == _normalize_project_type(project_type))
    return q.order_by(GcCapacityWindow.start_date).all()


@router.post("", response_model=GcCapacityWindowOut)
def create_gc_capacity_window(
    body: GcCapacityWindowCreate,
    staging_db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    pt = _normalize_project_type(body.project_type)
    _validate_single_geo_level(body.region, body.area, body.market)
    _validate_geo_hierarchy(
        staging_db, config_db, body.user_id, pt, body.vendor_name,
        body.region, body.area, body.market,
    )

    sd = _parse_required_date("start_date", body.start_date)
    ed = _parse_required_date("end_date", body.end_date)
    if sd >= ed:
        raise HTTPException(
            status_code=400,
            detail="start_date must be strictly before end_date.",
        )

    row = GcCapacityWindow(
        user_id=body.user_id,
        project_type=pt,
        start_date=sd,
        end_date=ed,
        market=body.market,
        area=body.area,
        region=body.region,
        vendor_name=body.vendor_name,
        max_sites=body.max_sites,
    )
    config_db.add(row)
    config_db.commit()
    config_db.refresh(row)
    return row


@router.put("/{entry_id}", response_model=GcCapacityWindowOut)
def update_gc_capacity_window(
    entry_id: int,
    body: GcCapacityWindowUpdate,
    user_id: str = Query(..., description="User ID"),
    staging_db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    row = (
        config_db.query(GcCapacityWindow)
        .filter(GcCapacityWindow.id == entry_id, GcCapacityWindow.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"GC capacity window {entry_id} not found")

    updates = body.model_dump(exclude_unset=True)

    if "project_type" in updates:
        updates["project_type"] = _normalize_project_type(updates["project_type"])
    new_project_type = updates.get("project_type", row.project_type)
    new_vendor_name = updates.get("vendor_name", row.vendor_name)

    new_region = updates.get("region", row.region)
    new_area = updates.get("area", row.area)
    new_market = updates.get("market", row.market)
    _validate_single_geo_level(new_region, new_area, new_market)
    _validate_geo_hierarchy(
        staging_db, config_db, user_id, new_project_type, new_vendor_name,
        new_region, new_area, new_market, exclude_id=entry_id,
    )

    for date_field in ("start_date", "end_date"):
        if date_field in updates and updates[date_field] is not None:
            updates[date_field] = _parse_required_date(date_field, updates[date_field])

    sd = updates.get("start_date", row.start_date)
    ed = updates.get("end_date", row.end_date)
    if sd >= ed:
        raise HTTPException(
            status_code=400,
            detail="start_date must be strictly before end_date.",
        )

    for field, value in updates.items():
        setattr(row, field, value)

    config_db.commit()
    config_db.refresh(row)
    return row


@router.delete("/{entry_id}")
def delete_gc_capacity_window(
    entry_id: int,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_config_db),
):
    row = (
        db.query(GcCapacityWindow)
        .filter(GcCapacityWindow.id == entry_id, GcCapacityWindow.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"GC capacity window {entry_id} not found")

    db.delete(row)
    db.commit()
    return {"detail": f"Deleted GC capacity window {entry_id}"}
