from datetime import date, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from .utils import parse_date
from .milestones import (
    get_milestones, get_prereq_tails, get_cx_start_offset_days,
    get_planned_start_column, apply_user_expected_days,
)


# ----------------------------------------------------------------
# Threshold helpers (percentage-based)
# ----------------------------------------------------------------

def _match_pct_threshold(pct: float, thresholds: List[Dict]) -> tuple[str, str]:
    """
    Walk *thresholds* in sort_order and return (status_label, color) for the
    first range that contains *pct*.  max_pct=None means unbounded above (100%).
    """
    for t in thresholds:
        lo = t["min_pct"]
        hi = t["max_pct"]
        if pct >= lo and (hi is None or pct <= hi):
            return t["status_label"], t["color"]
    return "IN PROGRESS", "orange"  # fallback


def compute_status(
    actual: Optional[date],
    pf: Optional[date],
    today: date,
    is_text_field=False,
    text_val=None,
):
    """
    Determine individual milestone status.

    Returns (status_label, delay_days).
    Milestone-level status is always: On Track / In Progress / Delayed.
    """
    if is_text_field:
        val = text_val or ""
        if val.strip():
            return "On Track", 0
        return "In Progress", 0

    if actual is not None:
        delay = (actual - pf).days if pf else 0
        if delay <= 0:
            return "On Track", delay
        return "Delayed", delay

    if pf is not None:
        remaining = (pf - today).days
        if remaining >= 0:
            return "In Progress", 0
        delay = abs(remaining)
        return "Delayed", delay

    return "In Progress", 0


def compute_overall_status(
    on_track_count: int,
    total_count: int,
    milestone_thresholds: List[Dict] | None = None,
) -> str:
    """
    Determine site-level overall status from the percentage of on-track milestones.

    Computes on_track_pct = (on_track_count / total_count) * 100 and matches
    it against DB-driven *milestone_thresholds* (percentage ranges).

    Falls back to hardcoded brackets if no thresholds are available.
    """
    if total_count == 0:
        return "ON TRACK"

    on_track_pct = (on_track_count / total_count) * 100

    if milestone_thresholds:
        label, _ = _match_pct_threshold(on_track_pct, milestone_thresholds)
        return label

    # fallback
    if on_track_pct >= 60:
        return "ON TRACK"
    elif on_track_pct >= 30:
        return "IN PROGRESS"
    return "CRITICAL"


# ----------------------------------------------------------------
# Column config handlers
#
# Each handler receives (row, column_config) and returns:
#   (actual_date_or_None, is_text: bool, text_val_or_None, skip_as_on_track: bool)
#
# skip_as_on_track=True means "this milestone is not applicable, mark On Track"
#
# To add a new type: define a handler and register it in COLUMN_HANDLERS.
# ----------------------------------------------------------------

def _handle_single(row: Dict, cfg: Dict):
    """Single date column."""
    col = cfg["columns"][0] if cfg.get("columns") else None
    actual = parse_date(row.get(col)) if col else None
    return actual, False, None, False


def _handle_max(row: Dict, cfg: Dict):
    """Multiple date columns — return latest (max) non-null date."""
    parsed = [parse_date(row.get(c)) for c in cfg.get("columns", [])]
    valid = [d for d in parsed if d is not None]
    if len(valid) >= 2:
        return max(valid), False, None, False
    return (valid[0] if valid else None), False, None, False


def _handle_text(row: Dict, cfg: Dict):
    """Text presence check — milestone is complete if the text field is populated."""
    col = cfg["columns"][0] if cfg.get("columns") else None
    text_val = (row.get(col) or "") if col else ""
    return None, True, text_val, False


def _handle_with_status(row: Dict, cfg: Dict):
    """
    Date + status column. Fully resolves skip/use_date/pending from cfg.

    cfg keys:
      columns  : [date_col, status_col]
      skip     : list of status values that mean "not applicable" → skip_as_on_track=True
      use_date : list of status values that mean "use the actual date"
      (anything else) → pending: actual=None
    """
    columns = cfg.get("columns", [])
    date_col = columns[0] if len(columns) > 0 else None
    status_col = columns[1] if len(columns) > 1 else None
    actual_date = parse_date(row.get(date_col)) if date_col else None
    status_val = (row.get(status_col) or "").strip() if status_col else ""

    skip_values = cfg.get("skip", [])
    use_date_values = cfg.get("use_date", [])

    if status_val in skip_values or (not status_val and "" in skip_values):
        return actual_date, False, None, True  # skip as On Track
    elif status_val in use_date_values:
        return actual_date, False, None, False  # use actual date
    else:
        return None, False, None, False  # pending


COLUMN_HANDLERS = {
    "single": _handle_single,
    "max": _handle_max,
    "text": _handle_text,
    "with_status": _handle_with_status,
}


def _get_actual_date(row: Dict, ms: Dict):
    """Extract actual date/value for a milestone using its column_config."""
    cfg = ms.get("column_config") or {}
    cfg_type = cfg.get("type", "single")
    handler = COLUMN_HANDLERS.get(cfg_type, _handle_single)
    return handler(row, cfg)


def _compute_planned_dates(
    origin_date: date,
    milestones: List[Dict],
    skipped_keys: set | None = None,
):
    """
    Compute planned start/finish for every milestone from the dependency chain.

    When a milestone key is in *skipped_keys* its duration is treated as zero
    (planned_finish == planned_start) so downstream milestones start earlier.

    For milestones that depend on more than one predecessor the latest (max)
    planned_finish across all dependencies is used as the anchor — this is the
    correct critical-path behaviour.

    For multi-dependency milestones the duration is the max of the predecessors'
    expected_days (e.g. BOM in BAT depends on Entitlement & Scoping Validated,
    so its duration = max(expected_days of those two)).
    """
    skipped = skipped_keys or set()
    dates = {}
    expected_by_key = {m["key"]: m["expected_days"] for m in milestones}

    for ms in milestones:
        key = ms["key"]
        dep = ms["depends_on"]
        gap = ms.get("start_gap_days", 1)

        if key in skipped:
            expected = 0
        elif dep is not None and isinstance(dep, list) and len(dep) > 1:
            # Multi-dependency: duration = max of predecessors' expected_days
            expected = max(expected_by_key.get(d, 0) for d in dep)
        else:
            expected = ms["expected_days"]

        if dep is None:
            dates[key] = {
                "ps": origin_date,
                "pf": origin_date + timedelta(days=expected) if expected > 0 else origin_date,
            }
            continue

        # Normalise to list so single and multi-dependency paths share logic
        dep_list = dep if isinstance(dep, list) else [dep]
        dep_finishes = [dates[d]["pf"] for d in dep_list if d in dates]
        if not dep_finishes:
            continue
        latest_dep_finish = max(dep_finishes)

        ps = latest_dep_finish + timedelta(days=gap)
        pf = ps + timedelta(days=expected)
        dates[key] = {"ps": ps, "pf": pf}

    return dates


def _build_dependency_maps(milestones_config: List[Dict]) -> tuple[Dict, Dict]:
    """
    Build preceding and following milestone name maps from the dependency graph.

    Returns:
        preceding_map: {key: [names of milestones this key depends on]}
        following_map: {key: [names of milestones that depend on this key]}

    For milestones with multiple predecessors (e.g. depends_on=["3710","1327"]),
    all predecessors are listed. The planned_start uses max(predecessor finish dates)
    as per the critical-path logic.
    """
    name_lookup = {m["key"]: m["name"] for m in milestones_config}
    preceding_map: Dict[str, List[str]] = {}
    following_map: Dict[str, List[str]] = {m["key"]: [] for m in milestones_config}

    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]
        if dep is None:
            preceding_map[key] = []
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        preceding_map[key] = [name_lookup.get(d, d) for d in dep_list]
        for d in dep_list:
            if d in following_map:
                following_map[d].append(name_lookup.get(key, key))

    return preceding_map, following_map


def _build_milestone_row(key, ms, ps, pf, actual, status, delay, days_since, days_remaining, is_text, text_val, preceding=None, following=None):
    """Build the milestone output dict."""
    return {
        "key": key,
        "name": ms["name"],
        "sort_order": ms["sort_order"],
        "expected_days": ms["expected_days"],
        "task_owner": ms.get("task_owner"),
        "phase_type": ms.get("phase_type"),
        "is_virtual": ms.get("is_virtual", False),
        "preceding_milestones": preceding or [],
        "following_milestones": following or [],
        "planned_start": str(ps) if ps else None,
        "planned_finish": str(pf) if pf else None,
        "actual_finish": (
            str(actual) if actual
            else (text_val if is_text and text_val else None)
        ),
        "delay_days": delay,
        "status": status,
    }


def compute_milestones_for_site(
    row: Dict,
    db: Session,
    skipped_keys: set | None = None,
    user_expected_days_overrides: dict | None = None,
) -> tuple[List[Dict], Optional[date]]:
    today = date.today()

    milestones_config = get_milestones(db)
    milestones_config = apply_user_expected_days(milestones_config, user_expected_days_overrides or {})
    prereq_tails = get_prereq_tails(db)
    cx_start_offset_days = get_cx_start_offset_days(db)
    planned_start_col = get_planned_start_column(db)
    origin_date = parse_date(row.get(planned_start_col))
    if origin_date is None:
        return [], None

    dates = _compute_planned_dates(origin_date, milestones_config, skipped_keys=skipped_keys)

    skipped = skipped_keys or set()
    preceding_map, following_map = _build_dependency_maps(milestones_config)
    milestones = []

    for ms in milestones_config:
        key = ms["key"]
        if key not in dates:
            continue
        ps = dates[key]["ps"]
        pf = dates[key]["pf"]

        preceding = preceding_map.get(key, [])
        following = following_map.get(key, [])

        # User-skipped prerequisite — excluded from response entirely
        # (planned dates still computed with 0 duration so downstream milestones shift)
        if key in skipped:
            continue

        actual, is_text, text_val, skip = _get_actual_date(row, ms)

        # Handler said "skip as On Track" (e.g. with_status where status = N/A)
        if skip:
            milestones.append(_build_milestone_row(
                key, ms, ps, pf,
                actual=actual, status="On Track", delay=0,
                days_since=None, days_remaining=None,
                is_text=False, text_val=None,
                preceding=preceding, following=following,
            ))
            continue

        # Standard processing
        status, delay = compute_status(
            actual, pf, today, is_text, text_val,
        )
        days_since = (today - actual).days if actual else None
        days_remaining = (pf - today).days if (actual is None and pf) else None

        milestones.append(_build_milestone_row(
            key, ms, ps, pf,
            actual=actual, status=status, delay=delay,
            days_since=days_since, days_remaining=days_remaining,
            is_text=is_text, text_val=text_val,
            preceding=preceding, following=following,
        ))

    # ----------------------------------------------------------------
    # All Prerequisites Complete
    # ----------------------------------------------------------------
    # Build a child→parents map for walking up the dependency chain
    child_to_parents: Dict[str, List[str]] = {}
    for ms in milestones_config:
        dep = ms["depends_on"]
        if dep is None:
            child_to_parents[ms["key"]] = []
        elif isinstance(dep, list):
            child_to_parents[ms["key"]] = dep
        else:
            child_to_parents[ms["key"]] = [dep]

    name_lookup = {m["key"]: m["name"] for m in milestones_config}
    tail_dates = []
    effective_tail_keys = []

    for tail in prereq_tails:
        key = tail["key"]
        offset = tail["offset_days"]

        if key not in skipped:
            # Tail is not skipped — use it directly
            if key in dates:
                pf_tail = dates[key]["pf"]
                tail_dates.append(pf_tail + timedelta(days=offset))
                effective_tail_keys.append(key)
        else:
            # Tail is skipped — walk up the dependency chain to find the
            # nearest non-skipped ancestor(s) and use them instead
            queue = list(child_to_parents.get(key, []))
            visited = {key}
            while queue:
                ancestor = queue.pop(0)
                if ancestor in visited:
                    continue
                visited.add(ancestor)
                if ancestor in skipped:
                    # This ancestor is also skipped, keep walking up
                    queue.extend(child_to_parents.get(ancestor, []))
                else:
                    # Found a non-skipped ancestor — use it as effective tail
                    if ancestor in dates:
                        pf_tail = dates[ancestor]["pf"]
                        tail_dates.append(pf_tail + timedelta(days=offset))
                        effective_tail_keys.append(ancestor)

    if not tail_dates:
        return milestones, None

    all_prereq_complete = max(tail_dates)

    # Collect effective tail milestone names for preceding_milestones
    all_prereq_preceding = [name_lookup.get(k, k) for k in effective_tail_keys]

    milestones.append({
        "key": "all_prereq",
        "name": "All Prerequisites Complete",
        "sort_order": 15,
        "expected_days": 0,
        "task_owner": None,
        "phase_type": "Ready for Cx Stage",
        "is_virtual": True,
        "preceding_milestones": all_prereq_preceding,
        "following_milestones": ["Cx Start Forecast"],
        "planned_start": str(all_prereq_complete),
        "planned_finish": str(all_prereq_complete),
        "actual_finish": None,
        "days_since": None,
        "days_remaining": (all_prereq_complete - today).days if all_prereq_complete else None,
        "delay_days": 0,
        "status": "In Progress" if all_prereq_complete >= today else "Delayed",
    })

    # ----------------------------------------------------------------
    # Forecasted CX Start
    # ----------------------------------------------------------------
    forecasted_cx_start = all_prereq_complete + timedelta(days=cx_start_offset_days)

    milestones.append({
        "key": "cx_start_forecast",
        "name": "Cx Start Forecast",
        "sort_order": 16,
        "expected_days": cx_start_offset_days,
        "task_owner": None,
        "phase_type": "Ready for Cx Stage",
        "is_virtual": True,
        "preceding_milestones": ["All Prerequisites Complete"],
        "following_milestones": [],
        "planned_start": str(all_prereq_complete + timedelta(days=1)),
        "planned_finish": str(forecasted_cx_start),
        "actual_finish": None,
        "days_since": None,
        "days_remaining": (forecasted_cx_start - today).days if forecasted_cx_start else None,
        "delay_days": 0,
        "status": "In Progress" if forecasted_cx_start >= today else "Delayed",
    })

    return milestones, forecasted_cx_start
