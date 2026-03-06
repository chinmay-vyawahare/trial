"""
Prerequisite (Milestone Definition) read-only APIs.

- GET /prerequisites       — list all prerequisites
- GET /prerequisites/{id}  — get single prerequisite by id

All create / update / delete operations are in the admin router.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import MilestoneDefinition
from app.schemas.gantt import MilestoneDefinitionOut

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
    """Build preceding/following milestone name maps from the dependency graph,
    resolving through skipped milestones (is_skipped=True)."""
    name_lookup = {r.key: r.name for r in rows}
    skipped_keys = {r.key for r in rows if r.is_skipped}

    # Build raw dependency graph by key
    raw_preceding: dict[str, list[str]] = {}
    for r in rows:
        dep = _parse_depends_on(r.depends_on)
        if dep is None:
            raw_preceding[r.key] = []
        else:
            dep_list = dep if isinstance(dep, list) else [dep]
            raw_preceding[r.key] = dep_list

    # Resolve preceding: walk through skipped predecessors to non-skipped ancestors
    def _resolve(key: str, visited: set | None = None) -> list[str]:
        if visited is None:
            visited = set()
        result = []
        for p in raw_preceding.get(key, []):
            if p in visited:
                continue
            visited.add(p)
            if p in skipped_keys:
                result.extend(_resolve(p, visited))
            else:
                result.append(p)
        return result

    preceding_map: dict[str, list[str]] = {}
    for r in rows:
        if r.key in skipped_keys:
            preceding_map[r.key] = []
        else:
            preceding_map[r.key] = [name_lookup.get(k, k) for k in _resolve(r.key)]

    # Build following as reverse of resolved preceding
    following_map: dict[str, list[str]] = {r.key: [] for r in rows}
    for r in rows:
        if r.key in skipped_keys:
            continue
        for p in _resolve(r.key):
            if p not in skipped_keys and p in following_map:
                following_map[p].append(name_lookup.get(r.key, r.key))

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
    all_rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    enriched = _enrich_with_dependencies(all_rows)
    return next(m for m in enriched if m["key"] == row.key)
