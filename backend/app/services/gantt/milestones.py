"""
Milestone definitions, prereq tails, and gantt config — loaded from DB.

Single source of truth: database tables seeded by init_milestone_data.py.
"""

import json
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models.prerequisite import MilestoneDefinition, MilestoneColumn, PrereqTail, GanttConfig, ConstraintThreshold, UserExpectedDays, UserHistoryExpectedDays


def _parse_json_or_str(raw: str):
    """Convert a DB string back to None / str / list."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _parse_logic(raw: str):
    """Parse the logic JSON column, return dict or None."""
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, ValueError):
        return None


def _build_columns_config(columns: list[dict]) -> dict:
    """
    Build the column_config dict from normalized MilestoneColumn rows.

    Returns the same structure that logic.py handlers expect:
      {"type": "single"|"max"|"text"|"with_status", "columns": [...], ...extra}

    This bridges the normalized DB schema to the handler interface.
    """
    if not columns:
        return {"type": "single", "columns": []}

    roles = {c["column_role"] for c in columns}
    date_cols = [c for c in columns if c["column_role"] == "date"]
    text_cols = [c for c in columns if c["column_role"] == "text"]
    status_cols = [c for c in columns if c["column_role"] == "status"]

    # --- text presence check ---
    if "text" in roles and not date_cols and not status_cols:
        return {
            "type": "text",
            "columns": [c["column_name"] for c in text_cols],
        }

    # --- date + status (with_status) ---
    if "status" in roles and date_cols:
        status_logic = _parse_logic(status_cols[0]["logic"]) if status_cols else {}
        return {
            "type": "with_status",
            "columns": [date_cols[0]["column_name"], status_cols[0]["column_name"]],
            "skip": (status_logic or {}).get("skip", []),
            "use_date": (status_logic or {}).get("use_date", []),
        }

    # --- multiple date columns with pick=max (latest date) ---
    if len(date_cols) > 1:
        has_max = any(
            (_parse_logic(c["logic"]) or {}).get("pick") == "max"
            for c in date_cols
        )
        if has_max:
            return {
                "type": "max",
                "columns": [c["column_name"] for c in date_cols],
            }

    # --- single date (default) ---
    return {
        "type": "single",
        "columns": [date_cols[0]["column_name"]] if date_cols else [],
    }


def get_milestones(db: Session) -> list[dict]:
    """Fetch milestone definitions with their columns from DB."""
    ms_rows = db.query(MilestoneDefinition).order_by(MilestoneDefinition.sort_order).all()
    col_rows = db.query(MilestoneColumn).order_by(MilestoneColumn.sort_order).all()

    # Group columns by milestone_key
    cols_by_key = defaultdict(list)
    for c in col_rows:
        cols_by_key[c.milestone_key].append({
            "column_name": c.column_name,
            "column_role": c.column_role,
            "logic": c.logic,
            "sort_order": c.sort_order,
        })

    result = []
    for r in ms_rows:
        ms_columns = cols_by_key.get(r.key, [])
        column_config = _build_columns_config(ms_columns)

        result.append({
            "key": r.key,
            "name": r.name,
            "sort_order": r.sort_order,
            "expected_days": r.expected_days,
            "depends_on": _parse_json_or_str(r.depends_on),
            "start_gap_days": r.start_gap_days if r.start_gap_days is not None else 1,
            "task_owner": r.task_owner,
            "phase_type": r.phase_type,
            "column_config": column_config,
        })
    return result


def get_user_expected_days_overrides(db: Session, user_id: str) -> dict[str, int]:
    """
    Return a {milestone_key: expected_days} map of user-level SLA overrides.

    Returns an empty dict if the user has no overrides.
    """
    if not user_id:
        return {}
    rows = (
        db.query(UserExpectedDays)
        .filter(UserExpectedDays.user_id == user_id)
        .all()
    )
    return {r.milestone_key: r.expected_days for r in rows}


def get_history_expected_days_overrides(db: Session) -> dict[str, int]:
    """
    Return a {milestone_key: history_expected_days} map from the
    milestone_definitions table (only where history_expected_days is set).
    """
    rows = (
        db.query(MilestoneDefinition.key, MilestoneDefinition.history_expected_days)
        .filter(MilestoneDefinition.history_expected_days.isnot(None))
        .all()
    )
    return {r[0]: r[1] for r in rows}


def get_history_expected_days_by_user(db: Session, user_id: str) -> dict[str, int]:
    """
    Return a {milestone_key: history_expected_days} map for a specific user
    from the user_history_expected_days table.

    Returns an empty dict if no user_id or no records found.
    """
    if not user_id:
        return {}
    rows = (
        db.query(UserHistoryExpectedDays)
        .filter(UserHistoryExpectedDays.user_id == user_id)
        .all()
    )
    return {r.milestone_key: r.history_expected_days for r in rows}


def save_user_history_expected_days(
    db: Session,
    user_id: str,
    history_results: list[dict],
    date_from=None,
    date_to=None,
) -> None:
    """
    Save computed history_expected_days for a user.

    Upserts each milestone's history_expected_days into user_history_expected_days.
    """
    if not user_id:
        return

    for item in history_results:
        computed = item.get("history_expected_days")
        effective = computed if computed is not None else 0

        existing = (
            db.query(UserHistoryExpectedDays)
            .filter(
                UserHistoryExpectedDays.user_id == user_id,
                UserHistoryExpectedDays.milestone_key == item["milestone_key"],
            )
            .first()
        )
        if existing:
            existing.history_expected_days = effective
            existing.milestone_name = item.get("milestone_name")
            existing.sample_count = item.get("sample_count", 0)
            if date_from:
                existing.date_from = date_from
            if date_to:
                existing.date_to = date_to
        else:
            row = UserHistoryExpectedDays(
                user_id=user_id,
                milestone_key=item["milestone_key"],
                milestone_name=item.get("milestone_name"),
                history_expected_days=effective,
                sample_count=item.get("sample_count", 0),
                date_from=date_from,
                date_to=date_to,
            )
            db.add(row)

    db.commit()


def apply_user_expected_days(milestones: list[dict], overrides: dict[str, int]) -> list[dict]:
    """
    Return a new milestones list with expected_days replaced by user overrides
    where applicable. Does NOT mutate the original list.
    """
    if not overrides:
        return milestones
    result = []
    for ms in milestones:
        if ms["key"] in overrides:
            ms = {**ms, "expected_days": overrides[ms["key"]]}
        result.append(ms)
    return result


def get_prereq_tails(db: Session) -> list[dict]:
    """Fetch prereq tails from DB."""
    rows = db.query(PrereqTail).all()
    return [{"key": r.milestone_key, "offset_days": r.offset_days} for r in rows]


def get_cx_start_offset_days(db: Session) -> int:
    """Fetch CX_START_OFFSET_DAYS from DB config."""
    row = db.query(GanttConfig).filter(GanttConfig.config_key == "CX_START_OFFSET_DAYS").first()
    return int(row.config_value) if row else 4


def get_planned_start_column(db: Session) -> str:
    """Fetch the staging table column name for the root milestone planned start date."""
    row = db.query(GanttConfig).filter(GanttConfig.config_key == "PLANNED_START_COLUMN").first()
    return row.config_value if row else "pj_p_3710_ran_entitlement_complete_finish"


def get_all_actual_columns(milestones: list[dict]) -> list[str]:
    """Collect every unique staging table column needed across all milestones."""
    columns = set()
    for ms in milestones:
        cfg = ms.get("column_config") or {}
        for col in cfg.get("columns", []):
            columns.add(col)
    return sorted(columns)


def get_milestone_thresholds(db: Session) -> list[dict]:
    """
    Load milestone-level constraint thresholds (count-based) from DB.

    Used to determine site overall status from pending milestone count.
    Each dict: {"status_label": str, "color": str, "min_pct": float, "max_pct": float|None}
    """
    rows = (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.constraint_type == "milestone")
        .order_by(ConstraintThreshold.sort_order)
        .all()
    )
    return [
        {
            "status_label": r.status_label,
            "color": r.color,
            "min_pct": r.min_pct,
            "max_pct": r.max_pct,
        }
        for r in rows
    ]


def get_overall_thresholds(db: Session) -> list[dict]:
    """
    Load dashboard-level constraint thresholds (count-based) from DB.

    Used to determine dashboard overall status from on-track site count.
    Each dict: {"status_label": str, "color": str, "min_pct": float, "max_pct": float|None}
    """
    rows = (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.constraint_type == "overall")
        .order_by(ConstraintThreshold.sort_order)
        .all()
    )
    return [
        {
            "status_label": r.status_label,
            "color": r.color,
            "min_pct": r.min_pct,
            "max_pct": r.max_pct,
        }
        for r in rows
    ]
