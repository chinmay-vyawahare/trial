"""
Per-user Pace Constraint CRUD endpoints.

Validation rules:
  - Only ONE geo level (region, area, or market) per constraint.
  - Cannot add a lower-level geo when a higher-level already covers it
    (e.g. region=CENTRAL exists → cannot add area=Heartland under CENTRAL).
  - Cannot add a higher-level geo when a lower-level already exists
    (e.g. market=CHICAGO exists → cannot add region=CENTRAL which contains CHICAGO).
  - start_date / end_date are optional — when omitted, the next ISO week
    (Monday–Sunday) is used at query time.

- GET    /pace-constraints?user_id=...        — list user's entries
- POST   /pace-constraints                    — create new entry
- PUT    /pace-constraints/{id}?user_id=...  — update entry
- DELETE /pace-constraints/{id}?user_id=...  — delete entry
- GET    /pace-constraints/geo-hierarchy      — region→area→market tree
"""

from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_config_db, get_db
from app.models.prerequisite import PaceConstraint
from app.schemas.gantt import PaceConstraintOut, PaceConstraintCreate, PaceConstraintUpdate
from app.services.gantt.queries import get_geo_hierarchy

router = APIRouter(
    prefix="/api/v1/schedular/pace-constraints",
    tags=["pace-constraints"],
)


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _next_week_range() -> tuple[date, date]:
    """Return (Monday, Sunday) of the next ISO week."""
    today = date.today()
    next_monday = today - timedelta(days=today.weekday()) + timedelta(weeks=1)
    next_sunday = next_monday + timedelta(days=6)
    return next_monday, next_sunday


def _validate_single_geo_level(region, area, market):
    """Ensure at most one geo level is provided."""
    filled = sum(1 for v in (region, area, market) if v and v.strip())
    if filled > 1:
        raise HTTPException(
            status_code=400,
            detail="Only one geo level (region, area, or market) can be set per constraint.",
        )


def _normalize_project_type(value: str | None) -> str:
    """Normalize and validate the project_type — only 'macro' or 'ahloa' allowed."""
    pt = (value or "macro").strip().lower()
    if pt not in ("macro", "ahloa"):
        raise HTTPException(
            status_code=400,
            detail="project_type must be 'macro' or 'ahloa'.",
        )
    return pt


def _validate_geo_hierarchy(
    staging_db: Session,
    config_db: Session,
    user_id: str,
    project_type: str,
    body_region: str | None,
    body_area: str | None,
    body_market: str | None,
    exclude_id: int | None = None,
):
    """
    Validate that the new/updated constraint does not conflict with existing ones.

    Hierarchy: region (highest) → area → market (lowest). Hierarchy and
    duplicate-conflict checks are scoped to the same project_type — a MACRO
    constraint and an AHLOA constraint on the same geo do not conflict.
    """
    geo = get_geo_hierarchy(staging_db, project_type=project_type)

    # Build lookups (all lowercase)
    market_to_area: dict[str, str] = {}
    market_to_region: dict[str, str] = {}
    area_to_region: dict[str, str] = {}

    for row in geo:
        r = row["region"].strip().lower()
        a = row["area"].strip().lower()
        m = row["market"].strip().lower()
        market_to_area[m] = a
        market_to_region[m] = r
        area_to_region[a] = r

    # Existing constraints for this user, restricted to the same project_type
    existing = (
        config_db.query(PaceConstraint)
        .filter(
            PaceConstraint.user_id == user_id,
            PaceConstraint.project_type == project_type,
        )
        .all()
    )
    if exclude_id:
        existing = [c for c in existing if c.id != exclude_id]

    new_region = (body_region or "").strip().lower()
    new_area = (body_area or "").strip().lower()
    new_market = (body_market or "").strip().lower()

    for c in existing:
        c_region = (c.region or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_market = (c.market or "").strip().lower()

        if new_region:
            if c_region == new_region:
                raise HTTPException(status_code=400, detail=f"A constraint for region '{body_region}' already exists.")
            if c_area and area_to_region.get(c_area) == new_region:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add region '{body_region}' — existing constraint covers area '{c.area}' which belongs to this region.",
                )
            if c_market and market_to_region.get(c_market) == new_region:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add region '{body_region}' — existing constraint covers market '{c.market}' which belongs to this region.",
                )

        elif new_area:
            if c_area == new_area:
                raise HTTPException(status_code=400, detail=f"A constraint for area '{body_area}' already exists.")
            parent_region = area_to_region.get(new_area)
            if c_region and c_region == parent_region:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add area '{body_area}' — existing constraint covers region '{c.region}' which is a higher hierarchy.",
                )
            if c_market and market_to_area.get(c_market) == new_area:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add area '{body_area}' — existing constraint covers market '{c.market}' which belongs to this area.",
                )

        elif new_market:
            if c_market == new_market:
                raise HTTPException(status_code=400, detail=f"A constraint for market '{body_market}' already exists.")
            parent_region = market_to_region.get(new_market)
            if c_region and c_region == parent_region:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add market '{body_market}' — existing constraint covers region '{c.region}' which is a higher hierarchy.",
                )
            parent_area = market_to_area.get(new_market)
            if c_area and c_area == parent_area:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add market '{body_market}' — existing constraint covers area '{c.area}' which is a higher hierarchy.",
                )


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@router.get("/geo-hierarchy")
def get_geo_hierarchy_endpoint(
    project_type: str = Query("macro", description="'macro' or 'ahloa'"),
    db: Session = Depends(get_db),
):
    """
    Return the region → area → market hierarchy from the staging table,
    filtered to rows visible under the given project_type. The frontend must
    pass the project_type for which the user is creating a pace constraint,
    otherwise AHLOA-only regions/markets won't appear in the dropdown.
    """
    pt = _normalize_project_type(project_type)
    geo = get_geo_hierarchy(db, project_type=pt)
    hierarchy: dict[str, dict[str, list[str]]] = {}
    for row in geo:
        hierarchy.setdefault(row["region"], {}).setdefault(row["area"], []).append(row["market"])
    return hierarchy


@router.get("", response_model=list[PaceConstraintOut])
def list_pace_constraints(
    user_id: str = Query(..., description="User ID"),
    project_type: str | None = Query(
        None,
        description="Optional 'macro' or 'ahloa' filter. Omit to list across both.",
    ),
    db: Session = Depends(get_config_db),
):
    """
    List a user's pace constraints, optionally filtered by project_type.

    If a constraint has no start_date/end_date, the response fills in
    the next ISO week (Monday–Sunday) so the frontend always sees dates.
    """
    q = db.query(PaceConstraint).filter(PaceConstraint.user_id == user_id)
    if project_type is not None:
        q = q.filter(PaceConstraint.project_type == _normalize_project_type(project_type))
    rows = q.order_by(PaceConstraint.start_date).all()

    monday, sunday = _next_week_range()
    result = []
    for r in rows:
        data = PaceConstraintOut.model_validate(r).model_dump()
        if data["start_date"] is None:
            data["start_date"] = datetime.combine(monday, datetime.min.time())
        if data["end_date"] is None:
            data["end_date"] = datetime.combine(sunday, datetime.min.time())
        result.append(data)
    return result


@router.post("", response_model=PaceConstraintOut)
def create_pace_constraint(
    body: PaceConstraintCreate,
    staging_db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """Create a new pace constraint for a user, scoped to body.project_type."""
    pt = _normalize_project_type(body.project_type)

    # Validate single geo level
    _validate_single_geo_level(body.region, body.area, body.market)

    # Validate geo hierarchy conflicts against existing constraints (same project_type)
    _validate_geo_hierarchy(
        staging_db, config_db, body.user_id, pt,
        body.region, body.area, body.market,
    )

    # Validate date pairing — both or neither
    if bool(body.start_date) != bool(body.end_date):
        raise HTTPException(
            status_code=400,
            detail="Either send both start_date and end_date, or send neither.",
        )

    # Parse optional dates
    sd = None
    ed = None
    if body.start_date:
        try:
            sd = datetime.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    if body.end_date:
        try:
            ed = datetime.fromisoformat(body.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

    if sd and ed and sd > ed:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    row = PaceConstraint(
        user_id=body.user_id,
        project_type=pt,
        start_date=sd,
        end_date=ed,
        market=body.market,
        area=body.area,
        region=body.region,
        max_sites=body.max_sites,
    )
    config_db.add(row)
    config_db.commit()
    config_db.refresh(row)
    return row


@router.put("/{entry_id}", response_model=PaceConstraintOut)
def update_pace_constraint(
    entry_id: int,
    body: PaceConstraintUpdate,
    user_id: str = Query(..., description="User ID"),
    staging_db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """Update a pace constraint (must belong to user)."""
    row = (
        config_db.query(PaceConstraint)
        .filter(PaceConstraint.id == entry_id, PaceConstraint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Pace constraint {entry_id} not found")

    updates = body.model_dump(exclude_unset=True)

    # Resolve effective project_type (existing row's value unless explicitly changed)
    new_project_type = _normalize_project_type(updates.get("project_type", row.project_type))
    updates["project_type"] = new_project_type

    # Validate geo if any geo field is being changed
    new_region = updates.get("region", row.region)
    new_area = updates.get("area", row.area)
    new_market = updates.get("market", row.market)
    _validate_single_geo_level(new_region, new_area, new_market)
    _validate_geo_hierarchy(
        staging_db, config_db, user_id, new_project_type,
        new_region, new_area, new_market, exclude_id=entry_id,
    )

    for date_field in ("start_date", "end_date"):
        if date_field in updates and updates[date_field] is not None:
            try:
                updates[date_field] = datetime.fromisoformat(updates[date_field])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {date_field} format. Use YYYY-MM-DD.")

    for field, value in updates.items():
        setattr(row, field, value)

    config_db.commit()
    config_db.refresh(row)
    return row


@router.delete("/{entry_id}")
def delete_pace_constraint(
    entry_id: int,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_config_db),
):
    """Delete a pace constraint (must belong to user)."""
    row = (
        db.query(PaceConstraint)
        .filter(PaceConstraint.id == entry_id, PaceConstraint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Pace constraint {entry_id} not found")

    db.delete(row)
    db.commit()
    return {"detail": f"Deleted pace constraint {entry_id}"}
