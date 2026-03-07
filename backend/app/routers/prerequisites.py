"""
Prerequisite (Milestone Definition) read-only APIs.

- GET /prerequisites            — list all prerequisites
- GET /prerequisites/flowchart  — Mermaid flowchart of the milestone dependency graph
- GET /prerequisites/{id}       — get single prerequisite by id

All create / update / delete operations are in the admin router.
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import MilestoneDefinition, PrereqTail, GanttConfig
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


@router.get("/flowchart", response_class=PlainTextResponse)
def prerequisite_flowchart(db: Session = Depends(get_config_db)):
    """
    Return a Mermaid flowchart showing the full milestone dependency graph.

    Includes: dependency edges, expected days, task owners, phase grouping,
    parallel tracks, prereq tails, and skipped milestones.
    """
    rows = db.query(MilestoneDefinition).order_by(MilestoneDefinition.sort_order).all()
    tail_rows = db.query(PrereqTail).all()
    cx_row = db.query(GanttConfig).filter(GanttConfig.config_key == "CX_START_OFFSET_DAYS").first()
    cx_offset = int(cx_row.config_value) if cx_row else 4

    tail_keys = {t.milestone_key: t.offset_days for t in tail_rows}

    # Build lookup
    ms_map = {}
    for r in rows:
        dep = _parse_depends_on(r.depends_on)
        ms_map[r.key] = {
            "name": r.name,
            "expected_days": r.expected_days,
            "depends_on": dep,
            "task_owner": r.task_owner or "—",
            "phase_type": r.phase_type or "Other",
            "is_skipped": r.is_skipped,
            "is_tail": r.key in tail_keys,
            "tail_offset": tail_keys.get(r.key, 0),
        }

    # Group milestones by phase
    phases: dict[str, list[str]] = {}
    for key, ms in ms_map.items():
        phase = ms["phase_type"]
        phases.setdefault(phase, []).append(key)

    lines = ["graph TD"]

    # Node definitions with styling info
    for key, ms in ms_map.items():
        label = ms["name"]
        days = ms["expected_days"]
        owner = ms["task_owner"]
        tail_tag = ""
        if ms["is_tail"]:
            tail_tag = f" | Tail +{ms['tail_offset']}d"

        node_label = f"{label}\\n({days}d | {owner}{tail_tag})"

        if ms["is_skipped"]:
            # Dashed node for skipped
            lines.append(f'    {key}[/"{node_label}"/]')
        elif ms["is_tail"]:
            lines.append(f'    {key}[("{node_label}")]')
        else:
            lines.append(f'    {key}["{node_label}"]')

    lines.append("")

    # Phase subgraphs
    for phase, keys in phases.items():
        safe_phase = phase.replace(" ", "_").replace("&", "and")
        lines.append(f'    subgraph {safe_phase}["{phase}"]')
        for key in keys:
            lines.append(f"        {key}")
        lines.append("    end")
    lines.append("")

    # Edges from dependency graph
    for key, ms in ms_map.items():
        dep = ms["depends_on"]
        if dep is None:
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        for d in dep_list:
            if d in ms_map:
                if ms["is_skipped"]:
                    lines.append(f"    {d} -.-> {key}")
                else:
                    lines.append(f"    {d} --> {key}")

    lines.append("")

    # CX Start node — all tails converge here
    if tail_keys:
        lines.append(f'    cx_start(("CX Start\\n(+{cx_offset}d after all tails)"))')
        for tk in tail_keys:
            if tk in ms_map:
                lines.append(f"    {tk} ==> cx_start")
        lines.append("")

    # Styling
    lines.append("    %% Styling")
    for key, ms in ms_map.items():
        if ms["is_skipped"]:
            lines.append(f"    style {key} stroke-dasharray: 5 5,fill:#f9f9f9,color:#999")
        elif ms["is_tail"]:
            lines.append(f"    style {key} fill:#e1f5fe,stroke:#0288d1")

    # Root node styling
    root_keys = [k for k, ms in ms_map.items() if ms["depends_on"] is None]
    for rk in root_keys:
        lines.append(f"    style {rk} fill:#c8e6c9,stroke:#388e3c")

    # CX Start styling
    if tail_keys:
        lines.append("    style cx_start fill:#fff3e0,stroke:#f57c00,stroke-width:3px")

    return "\n".join(lines)


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
