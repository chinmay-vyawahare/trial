"""
Prerequisite (Milestone Definition) management APIs.

- GET    /prerequisites              — list all prerequisites
- GET    /prerequisites/{id}         — get single prerequisite by id
- PUT    /prerequisites/{id}         — update a prerequisite (name, expected_days, start_gap_days, task_owner, phase_type)
- PUT    /prerequisites/reorder      — bulk-reorder all prerequisites
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import MilestoneDefinition
from app.schemas.gantt import (
    MilestoneDefinitionOut,
    MilestoneDefinitionUpdate,
    MilestoneReorderRequest,
)

router = APIRouter(
    prefix="/api/v1/schedular/prerequisites",
    tags=["prerequisites"],
)


def _parse_depends_on(raw: str):
    """Convert DB depends_on string to None / str / list."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _enrich_with_dependencies(rows: list[MilestoneDefinition]) -> list[dict]:
    """
    Convert DB rows to dicts enriched with preceding_milestones / following_milestones.

    preceding_milestones  — names of milestones this one depends on (before this milestone)
    following_milestones  — names of milestones that depend on this one (after this milestone)
    """
    name_lookup = {r.key: r.name for r in rows}

    # Build following map: for each key, collect names of milestones that depend on it
    following_map: dict[str, list[str]] = {r.key: [] for r in rows}
    preceding_map: dict[str, list[str]] = {}

    for r in rows:
        dep = _parse_depends_on(r.depends_on)
        if dep is None:
            preceding_map[r.key] = []
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        preceding_map[r.key] = [name_lookup.get(d, d) for d in dep_list]
        for d in dep_list:
            if d in following_map:
                following_map[d].append(name_lookup.get(r.key, r.key))

    result = []
    for r in rows:
        data = MilestoneDefinitionOut.model_validate(r).model_dump()
        data["preceding_milestones"] = preceding_map.get(r.key, [])
        data["following_milestones"] = following_map.get(r.key, [])
        result.append(data)
    return result


@router.get("", response_model=list[MilestoneDefinitionOut])
def list_prerequisites(db: Session = Depends(get_config_db)):
    """Return every milestone definition ordered by sort_order."""
    rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    return _enrich_with_dependencies(rows)


@router.get("/{prerequisite_id}", response_model=MilestoneDefinitionOut)
def get_prerequisite(prerequisite_id: int, db: Session = Depends(get_config_db)):
    """Return a single milestone definition by its id."""
    row = db.query(MilestoneDefinition).filter(MilestoneDefinition.id == prerequisite_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Prerequisite with id {prerequisite_id} not found")
    # Need all rows to compute dependency graph
    all_rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    enriched = _enrich_with_dependencies(all_rows)
    return next(m for m in enriched if m["key"] == row.key)


@router.put("/{prerequisite_id}", response_model=MilestoneDefinitionOut)
def update_prerequisite(
    prerequisite_id: int,
    body: MilestoneDefinitionUpdate,
    db: Session = Depends(get_config_db),
):
    """
    Update any editable field on a milestone definition by its id.

    Accepts partial updates — only the fields present in the request body
    will be changed.
    """
    row = db.query(MilestoneDefinition).filter(MilestoneDefinition.id == prerequisite_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Prerequisite with id {prerequisite_id} not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)

    # Re-compute dependency graph after update
    all_rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    enriched = _enrich_with_dependencies(all_rows)
    return next(m for m in enriched if m["key"] == row.key)


# @router.put("/reorder/bulk", response_model=list[MilestoneDefinitionOut])
# def reorder_prerequisites(
#     body: MilestoneReorderRequest,
#     db: Session = Depends(get_config_db),
# ):
#     """
#     Bulk-reorder prerequisites.

#     Accepts a list of {key, sort_order} pairs.  Every milestone referenced
#     gets its sort_order updated.  Milestones NOT in the list keep their
#     current sort_order.

#     After the update, a consistency pass shifts any remaining milestones
#     so that all sort_order values form a gap-free 1-based sequence.
#     """
#     # Build a lookup for the incoming sort orders
#     incoming = {item.key: item.sort_order for item in body.items}

#     all_rows = (
#         db.query(MilestoneDefinition)
#         .order_by(MilestoneDefinition.sort_order)
#         .all()
#     )

#     # Apply the incoming sort_order values
#     for row in all_rows:
#         if row.key in incoming:
#             row.sort_order = incoming[row.key]

#     # Re-normalise: sort by the (possibly updated) sort_order, then reassign
#     # a clean 1-based sequence so there are no gaps or duplicates.
#     all_rows.sort(key=lambda r: r.sort_order)
#     for idx, row in enumerate(all_rows, start=1):
#         row.sort_order = idx

#     db.commit()

#     # Return the freshly ordered list with dependency info
#     refreshed = (
#         db.query(MilestoneDefinition)
#         .order_by(MilestoneDefinition.sort_order)
#         .all()
#     )
#     return _enrich_with_dependencies(refreshed)
