"""
Admin-only APIs for prerequisite management.

All create / update / delete operations on prerequisites, skip-prerequisites,
and prereq tails are admin-only.

- POST   /admin/prerequisites                              — create a new prerequisite
- PUT    /admin/prerequisites/{id}                         — update a prerequisite
- DELETE /admin/prerequisites/{id}                         — delete a prerequisite
- POST   /admin/skip-prerequisites                         — skip a prerequisite globally
- GET    /admin/skip-prerequisites                         — list all globally skipped prerequisites
- DELETE /admin/skip-prerequisites/{milestone_key}         — un-skip a prerequisite globally
- DELETE /admin/skip-prerequisites                         — un-skip all prerequisites globally
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import (
    MilestoneDefinition, MilestoneColumn, PrereqTail,
)
from app.schemas.gantt import (
    MilestoneDefinitionOut,
    MilestoneDefinitionUpdate,
    MilestoneDefinitionCreate,
    MilestoneDefinitionCreateOut,
    SkipPrerequisiteRequest,
    SkipPrerequisiteOut,
)

router = APIRouter(
    prefix="/api/v1/schedular/admin",
    tags=["admin"],
)


# ----------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------

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
    """Build preceding/following milestone name maps from the dependency graph."""
    name_lookup = {r.key: r.name for r in rows}
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


def _sync_prereq_tails(db: Session):
    """
    Auto-sync the prereq_tails table based on the current dependency graph.

    A milestone is a tail (contributes to "All Prerequisites Complete") when
    no other milestone depends on it — i.e. it has no followers in the graph.

    When a new milestone is added after an existing tail (making the old tail
    no longer a leaf), the new tail inherits the offset_days from the old one.

    Examples:
      - Add "X" depending on tail "3925" (offset=4) → "3925" is no longer a
        tail, "X" becomes the new tail with offset=4.
      - Delete a leaf milestone → its parent may become a new leaf tail.
        The new tail inherits the deleted one's offset.
    """
    all_rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )

    # Build parent→children map and find which keys are depended upon
    depended_upon = set()
    parent_to_children: dict[str, list[str]] = {}
    child_to_parents: dict[str, list[str]] = {}
    for r in all_rows:
        dep = _parse_depends_on(r.depends_on)
        if dep is None:
            child_to_parents[r.key] = []
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        child_to_parents[r.key] = dep_list
        depended_upon.update(dep_list)
        for d in dep_list:
            parent_to_children.setdefault(d, []).append(r.key)

    # Leaf milestones = those not depended upon by anyone
    all_keys = {r.key for r in all_rows}
    leaf_keys = all_keys - depended_upon

    # Load current tails and their offsets
    current_tails = {t.milestone_key: t for t in db.query(PrereqTail).all()}

    # Track offsets from tails that are about to be removed (no longer leaves)
    # so we can inherit them to their new leaf descendants
    removed_offsets: dict[str, int] = {}
    for key, tail in current_tails.items():
        if key not in leaf_keys:
            removed_offsets[key] = tail.offset_days
            db.delete(tail)

    # Add new tails for new leaves
    for key in leaf_keys:
        if key in current_tails:
            continue  # already exists, keep its offset

        # Try to inherit offset from a removed ancestor tail
        inherited_offset = 0
        parents = child_to_parents.get(key, [])
        for p in parents:
            if p in removed_offsets:
                inherited_offset = removed_offsets[p]
                break
        # If not a direct parent, walk up the chain
        if inherited_offset == 0:
            visited = set()
            queue = list(parents)
            while queue:
                ancestor = queue.pop(0)
                if ancestor in visited:
                    continue
                visited.add(ancestor)
                if ancestor in removed_offsets:
                    inherited_offset = removed_offsets[ancestor]
                    break
                queue.extend(child_to_parents.get(ancestor, []))

        db.add(PrereqTail(milestone_key=key, offset_days=inherited_offset))

    db.flush()


def _recompute_and_persist_dependencies(db: Session):
    """Recompute preceding/following and persist to DB for all milestones."""
    refreshed = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    enriched = _enrich_with_dependencies(refreshed)
    for item in enriched:
        ms_row = next((r for r in refreshed if r.key == item["key"]), None)
        if ms_row:
            ms_row.preceding_milestones = json.dumps(item.get("preceding_milestones", []))
            ms_row.following_milestones = json.dumps(item.get("following_milestones", []))
    return refreshed, enriched


# ----------------------------------------------------------------
# Prerequisite CRUD (admin only)
# ----------------------------------------------------------------

@router.post("/prerequisites", response_model=MilestoneDefinitionCreateOut)
def create_prerequisite(
    body: MilestoneDefinitionCreate,
    db: Session = Depends(get_config_db),
):
    """
    Create a new prerequisite and insert it into the flow.

    Accepts preceding_milestone_keys, following_milestone_keys, columns, etc.
    Auto-syncs prereq_tails after creation.
    """
    # --- Validate key uniqueness ---
    existing = db.query(MilestoneDefinition).filter(MilestoneDefinition.key == body.key).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Milestone key '{body.key}' already exists")

    all_rows = (
        db.query(MilestoneDefinition)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )
    key_lookup = {r.key: r for r in all_rows}

    # --- Validate preceding_milestone_keys ---
    preceding_keys = body.preceding_milestone_keys or []
    for pk in preceding_keys:
        if pk not in key_lookup:
            raise HTTPException(status_code=404, detail=f"Preceding milestone key '{pk}' not found")

    # --- Validate following_milestone_keys ---
    following_keys = body.following_milestone_keys or []
    for fk in following_keys:
        if fk not in key_lookup:
            raise HTTPException(status_code=404, detail=f"Following milestone key '{fk}' not found")

    # --- Build depends_on from preceding_milestone_keys ---
    if len(preceding_keys) == 0:
        depends_on = None
    elif len(preceding_keys) == 1:
        depends_on = preceding_keys[0]
    else:
        depends_on = json.dumps(preceding_keys)

    # --- Determine insert_after_key (for sort_order) ---
    insert_after_key = body.insert_after_key
    if insert_after_key is None and preceding_keys:
        insert_after_key = max(preceding_keys, key=lambda k: key_lookup[k].sort_order)

    # --- Compute sort_order and shift subsequent milestones ---
    if insert_after_key is not None:
        anchor = key_lookup.get(insert_after_key)
        if not anchor:
            raise HTTPException(status_code=404, detail=f"insert_after_key '{insert_after_key}' not found")
        new_sort_order = anchor.sort_order + 1
        for r in all_rows:
            if r.sort_order >= new_sort_order:
                r.sort_order += 1
    else:
        max_order = max((r.sort_order for r in all_rows), default=0)
        new_sort_order = max_order + 1

    # --- Rewire following milestones ---
    for fk in following_keys:
        r = key_lookup[fk]
        dep = _parse_depends_on(r.depends_on)

        if dep is None:
            r.depends_on = body.key
        elif isinstance(dep, list):
            new_dep = []
            replaced = False
            for d in dep:
                if d in preceding_keys and not replaced:
                    new_dep.append(body.key)
                    replaced = True
                elif d in preceding_keys:
                    continue
                else:
                    new_dep.append(d)
            if not replaced:
                new_dep.append(body.key)
            seen = set()
            deduped = [d for d in new_dep if d not in seen and not seen.add(d)]
            r.depends_on = json.dumps(deduped) if len(deduped) > 1 else deduped[0]
        else:
            r.depends_on = body.key

    # --- Create the milestone definition ---
    new_ms = MilestoneDefinition(
        key=body.key,
        name=body.name,
        sort_order=new_sort_order,
        expected_days=body.expected_days,
        depends_on=depends_on,
        start_gap_days=body.start_gap_days,
        task_owner=body.task_owner,
        phase_type=body.phase_type,
    )
    db.add(new_ms)
    db.flush()

    # --- Create milestone columns ---
    col_dicts = []
    for idx, col in enumerate(body.columns, start=1):
        mc = MilestoneColumn(
            milestone_key=body.key,
            column_name=col.column_name,
            column_role=col.column_role,
            logic=col.logic,
            sort_order=idx,
        )
        db.add(mc)
        col_dicts.append({
            "column_name": col.column_name,
            "column_role": col.column_role,
            "logic": col.logic,
            "sort_order": idx,
        })

    # --- Recompute dependencies and sync tails ---
    db.flush()
    _, enriched = _recompute_and_persist_dependencies(db)
    _sync_prereq_tails(db)

    db.commit()
    db.refresh(new_ms)

    new_enriched = next(m for m in enriched if m["key"] == body.key)
    return {
        **new_enriched,
        "depends_on": depends_on,
        "columns": col_dicts,
    }


@router.put("/prerequisites/{prerequisite_id}", response_model=MilestoneDefinitionOut)
def update_prerequisite(
    prerequisite_id: int,
    body: MilestoneDefinitionUpdate,
    db: Session = Depends(get_config_db),
):
    """
    Update a prerequisite. Auto-syncs prereq_tails after update.
    """
    row = db.query(MilestoneDefinition).filter(MilestoneDefinition.id == prerequisite_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Prerequisite with id {prerequisite_id} not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)

    db.flush()
    _, enriched = _recompute_and_persist_dependencies(db)
    _sync_prereq_tails(db)

    db.commit()
    db.refresh(row)

    return next(m for m in enriched if m["key"] == row.key)


# ----------------------------------------------------------------
# Skip prerequisites (admin only — global, affects real data)
# ----------------------------------------------------------------

@router.post("/skip-prerequisites", response_model=SkipPrerequisiteOut)
def skip_prerequisite(
    body: SkipPrerequisiteRequest,
    db: Session = Depends(get_config_db),
):
    """
    Globally skip a prerequisite by setting is_skipped=True on the milestone definition.

    This affects all users — skipped milestones are excluded from responses and counting.
    """
    ms = (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.key == body.milestone_key)
        .first()
    )
    if not ms:
        raise HTTPException(status_code=404, detail=f"Milestone '{body.milestone_key}' not found")

    ms.is_skipped = True
    db.commit()
    db.refresh(ms)
    return ms


@router.get("/skip-prerequisites", response_model=list[SkipPrerequisiteOut])
def list_skipped_prerequisites(db: Session = Depends(get_config_db)):
    """Return all globally skipped prerequisites."""
    return (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.is_skipped == True)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )


@router.delete("/skip-prerequisites/{milestone_key}")
def unskip_prerequisite(
    milestone_key: str,
    db: Session = Depends(get_config_db),
):
    """Un-skip a single prerequisite globally."""
    ms = (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.key == milestone_key)
        .first()
    )
    if not ms:
        raise HTTPException(status_code=404, detail=f"Milestone '{milestone_key}' not found")
    if not ms.is_skipped:
        raise HTTPException(status_code=404, detail=f"Milestone '{milestone_key}' is not skipped")

    ms.is_skipped = False
    db.commit()
    return {"detail": f"Un-skipped '{milestone_key}' globally"}


@router.delete("/skip-prerequisites")
def unskip_all_prerequisites(db: Session = Depends(get_config_db)):
    """Un-skip all prerequisites globally."""
    updated = (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.is_skipped == True)
        .update({"is_skipped": False})
    )
    db.commit()
    if updated == 0:
        raise HTTPException(status_code=404, detail="No skipped prerequisites found")
    return {"detail": f"Un-skipped all prerequisites globally, updated {updated} entries"}
