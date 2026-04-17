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
            "back_days": r.back_days,
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
    return {r.milestone_key: r.expected_days for r in rows if r.expected_days is not None}


def get_user_back_days_overrides(db: Session, user_id: str) -> dict[str, int]:
    """
    Return a {milestone_key: back_days} map of user-level back_days overrides.

    Used by the actual (right-to-left) view to anchor each milestone's planned
    finish at `cx_start - back_days`. An empty dict means: fall back to the
    global back_days persisted on MilestoneDefinition.
    """
    if not user_id:
        return {}
    rows = (
        db.query(UserExpectedDays)
        .filter(UserExpectedDays.user_id == user_id)
        .all()
    )
    return {r.milestone_key: r.back_days for r in rows if r.back_days is not None}


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


def get_user_history_back_days_overrides(db: Session, user_id: str) -> dict[str, int]:
    """
    Return a {milestone_key: back_days} map from user_history_expected_days.

    Used by the actual (right-to-left) view to anchor each milestone's
    planned finish at `cx_actual - back_days` from the historical sample.
    """
    if not user_id:
        return {}
    rows = (
        db.query(UserHistoryExpectedDays)
        .filter(UserHistoryExpectedDays.user_id == user_id)
        .all()
    )
    return {r.milestone_key: r.back_days for r in rows if r.back_days is not None}


def save_user_history_expected_days(
    db: Session,
    user_id: str,
    history_results: list[dict],
    date_from=None,
    date_to=None,
    view_type: str = "forecast",
) -> None:
    """
    Save computed history values for a user.

    Upserts each milestone into user_history_expected_days. The destination
    column depends on view_type:
      - "forecast" → history_expected_days  (left-to-right median)
      - "actual"   → back_days              (right-to-left median, cx_actual - ms_actual)

    Both columns can coexist per (user, milestone) so successive forecast/actual
    runs do not overwrite each other.
    """
    if not user_id:
        return

    is_actual = view_type == "actual"

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
            existing.milestone_name = item.get("milestone_name")
            existing.sample_count = item.get("sample_count", 0)
            if is_actual:
                existing.back_days = computed   # may be None for text milestones
            else:
                existing.history_expected_days = effective
            if date_from:
                existing.date_from = date_from
            if date_to:
                existing.date_to = date_to
        else:
            row = UserHistoryExpectedDays(
                user_id=user_id,
                milestone_key=item["milestone_key"],
                milestone_name=item.get("milestone_name"),
                history_expected_days=(0 if is_actual else effective),
                back_days=(computed if is_actual else None),
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


# ----------------------------------------------------------------
# back_days recomputation helpers
# ----------------------------------------------------------------

def recompute_back_days(
    db: Session,
    skipped_keys: set | None = None,
    user_expected_days_overrides: dict | None = None,
) -> dict[str, int]:
    """
    Run the right-to-left dependency walk once against a sentinel CX start
    date and return a {milestone_key: back_days} map.

    Reuses the same backward algorithm used per-request in the actual view
    (`_compute_planned_dates_backward` in gantt.logic), so values stay
    consistent between the persisted snapshot and an ad-hoc recompute.
    """
    # Local import to avoid circular dependency: logic.py imports from milestones.py.
    from datetime import date as _date
    from .logic import _compute_planned_dates_backward

    sentinel_cx = _date(2100, 1, 1)
    milestones = get_milestones(db)
    milestones = apply_user_expected_days(milestones, user_expected_days_overrides or {})
    tails = get_prereq_tails(db)

    dates = _compute_planned_dates_backward(
        sentinel_cx, milestones, tails, skipped_keys=skipped_keys,
    )
    return {key: (sentinel_cx - d["pf"]).days for key, d in dates.items()}


def persist_global_back_days(db: Session) -> None:
    """
    Recompute back_days using the GLOBAL skip set + global expected_days
    (no per-user overrides) and persist onto each MilestoneDefinition row.

    Call after any admin mutation that shifts the chain: is_skipped flip,
    expected_days edit, depends_on edit, or milestone create/delete.
    """
    global_skipped = {
        r.key for r in db.query(MilestoneDefinition.key, MilestoneDefinition.is_skipped)
        .filter(MilestoneDefinition.is_skipped == True).all()
    }
    back_days_map = recompute_back_days(db, skipped_keys=global_skipped)

    rows = db.query(MilestoneDefinition).all()
    for r in rows:
        new_val = back_days_map.get(r.key)
        if r.back_days != new_val:
            r.back_days = new_val
    db.flush()


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


def get_milestone_thresholds(db: Session, project_type: str = "macro") -> list[dict]:
    """
    Load milestone-level constraint thresholds from DB.
    Uses AhloaConstraintThreshold when project_type='ahloa'.
    """
    if project_type == "ahloa":
        from app.models.ahloa import AhloaConstraintThreshold
        rows = (
            db.query(AhloaConstraintThreshold)
            .filter(AhloaConstraintThreshold.constraint_type == "milestone",
                    AhloaConstraintThreshold.project_type == "ahloa")
            .order_by(AhloaConstraintThreshold.sort_order)
            .all()
        )
    else:
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


def get_overall_thresholds(db: Session, project_type: str = "macro") -> list[dict]:
    """
    Load dashboard-level constraint thresholds from DB.
    Uses AhloaConstraintThreshold when project_type='ahloa'.
    """
    if project_type == "ahloa":
        from app.models.ahloa import AhloaConstraintThreshold
        rows = (
            db.query(AhloaConstraintThreshold)
            .filter(AhloaConstraintThreshold.constraint_type == "overall",
                    AhloaConstraintThreshold.project_type == "ahloa")
            .order_by(AhloaConstraintThreshold.sort_order)
            .all()
        )
    else:
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
