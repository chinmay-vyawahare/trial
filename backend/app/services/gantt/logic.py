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
    first range that contains *pct*.  max_pct=None means unbounded above.
    min_pct / max_pct are percentage values (0-100).
    """
    for t in thresholds:
        lo = t["min_pct"]
        hi = t["max_pct"]
        if pct >= lo and (hi is None or pct <= hi):
            return t["status_label"], t["color"]
    return "IN PROGRESS", "orange"  # fallback


def get_milestone_range_for_status(
    status_label: str,
    total_milestones: int,
    thresholds: List[Dict],
) -> str:
    """
    Return a string like '9-14/14' showing the on-track milestone count range
    that corresponds to the given status_label for a site with total_milestones.
    """
    import math
    for t in thresholds:
        if t["status_label"] == status_label:
            lo = math.ceil(t["min_pct"] / 100 * total_milestones) if total_milestones > 0 else 0
            hi = math.floor(t["max_pct"] / 100 * total_milestones) if (t["max_pct"] is not None and total_milestones > 0) else total_milestones
            return f"{lo}-{hi}/{total_milestones}"
    # fallback
    return f"0-{total_milestones}/{total_milestones}"


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
    Determine site-level overall status from the on-track milestone percentage.

    Computes on-track percentage and matches against DB-driven *milestone_thresholds*
    (percentage ranges). Higher on-track % = better status.

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


def is_site_blocked(row: Dict) -> bool:
    """
    A site is blocked if either delay comments or delay code is present.
    """
    comments = (row.get("pj_construction_start_delay_comments") or "").strip()
    code = (row.get("pj_construction_complete_delay_code") or "").strip()
    return bool(comments or code)


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
    row: Dict | None = None,
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

    When *row* is provided and a predecessor has an actual finish date (non-text),
    actual_finish + 1 day is used as the planned start for the following milestone
    instead of the computed planned_finish + gap.
    """
    skipped = skipped_keys or set()
    dates = {}
    expected_by_key = {m["key"]: m["expected_days"] for m in milestones}

    # Pre-compute actual finish dates for all milestones (non-text only)
    actual_dates_by_key: Dict[str, date] = {}
    if row is not None:
        for ms in milestones:
            actual, is_text, text_val, skip = _get_actual_date(row, ms)
            if actual is not None and not is_text:
                actual_dates_by_key[ms["key"]] = actual

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

        # For each dependency, use actual_finish + 1 if available, else planned_finish + gap
        dep_anchors = []
        for d in dep_list:
            if d in actual_dates_by_key:
                # Predecessor has a real (non-text) actual finish date → use it + 1 day
                dep_anchors.append(actual_dates_by_key[d] + timedelta(days=1))
            elif d in dates:
                dep_anchors.append(dates[d]["pf"] + timedelta(days=gap))

        if not dep_anchors:
            continue
        ps = max(dep_anchors)
        pf = ps + timedelta(days=expected)
        dates[key] = {"ps": ps, "pf": pf}

    return dates


def _compute_planned_dates_backward(
    cx_start_date: date,
    milestones: List[Dict],
    prereq_tails: List[Dict],
    skipped_keys: set | None = None,
):
    """
    Compute planned finish dates backward from a known CX start date.

    In the forward view the chain is:
      tail.pf + tail_offset → All Prereq Complete + CX_START_OFFSET → CX Start

    In backward we reverse that — but CX_START_OFFSET_DAYS is NOT used here
    because the actual CX start date already accounts for any buffer.
    We go directly: tail.pf = cx_start_date − tail_offset_days.

    The result is the same dict structure as _compute_planned_dates: {key: {"ps": date, "pf": date}}
    """
    skipped = skipped_keys or set()

    # Build key→milestone lookup
    ms_by_key = {m["key"]: m for m in milestones}

    # Build forward dependency map: parent → [children that depend on it]
    children_of: Dict[str, List[str]] = {m["key"]: [] for m in milestones}
    for ms in milestones:
        dep = ms["depends_on"]
        if dep is None:
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        for d in dep_list:
            if d in children_of:
                children_of[d].append(ms["key"])

    # Identify tail milestone keys and their offsets
    tail_offsets = {t["key"]: t["offset_days"] for t in prereq_tails}

    # Start from tails: pf = cx_start_date − tail_offset
    # No CX_START_OFFSET_DAYS subtracted — it is only used in forward view.
    dates: Dict[str, Dict] = {}
    queue = []

    for tail_key, offset in tail_offsets.items():
        if tail_key not in ms_by_key:
            continue
        ms = ms_by_key[tail_key]
        expected = 0 if tail_key in skipped else ms["expected_days"]
        pf = cx_start_date - timedelta(days=offset)
        ps = pf - timedelta(days=expected) if expected > 0 else pf
        dates[tail_key] = {"ps": ps, "pf": pf}

        # Queue predecessors of this tail
        dep = ms["depends_on"]
        if dep is not None:
            dep_list = dep if isinstance(dep, list) else [dep]
            for d in dep_list:
                queue.append((d, tail_key))

    # Walk backward: each step from child to parent subtracts child.expected_days.
    # parent.pf = child.pf - child.expected_days
    # - Tail milestones keep their own offset — never overwritten by child tails.
    # - No gap days, no CX_START_OFFSET_DAYS in backward.
    # - When a parent gets tightened, re-queue its predecessors to propagate.
    while queue:
        parent_key, child_key = queue.pop(0)
        if parent_key not in ms_by_key:
            continue

        # Skip if parent is itself a tail — it has its own offset from CX
        if parent_key in tail_offsets:
            continue

        child_ms = ms_by_key[child_key]
        child_pf = dates[child_key]["pf"] if child_key in dates else cx_start_date
        child_expected = child_ms["expected_days"]
        candidate_pf = child_pf - timedelta(days=child_expected)

        updated = False
        if parent_key in dates:
            # Take the earliest (min) if multiple children constrain this parent
            if candidate_pf < dates[parent_key]["pf"]:
                dates[parent_key]["pf"] = candidate_pf
                dates[parent_key]["ps"] = candidate_pf
                updated = True
        else:
            dates[parent_key] = {"ps": candidate_pf, "pf": candidate_pf}
            updated = True

        # Always propagate upward when parent is new or tightened
        if updated:
            parent_ms = ms_by_key[parent_key]
            dep = parent_ms["depends_on"]
            if dep is not None:
                dep_list = dep if isinstance(dep, list) else [dep]
                for d in dep_list:
                    queue.append((d, parent_key))

    # ----------------------------------------------------------------
    # Second pass: milestones not reachable from tails (e.g. 3850, 3875)
    # Compute them forward from their already-computed predecessors.
    # Repeat until no new milestones are resolved (handles chains like 3850→3875).
    # ----------------------------------------------------------------
    changed = True
    while changed:
        changed = False
        for ms in milestones:
            key = ms["key"]
            if key in dates:
                continue
            dep = ms["depends_on"]
            if dep is None:
                continue
            dep_list = dep if isinstance(dep, list) else [dep]
            # Forward fill: this milestone's pf = predecessor.pf + this milestone's expected_days
            dep_anchors = []
            for d in dep_list:
                if d in dates:
                    dep_anchors.append(dates[d]["pf"] + timedelta(days=ms["expected_days"]))
            if not dep_anchors:
                continue
            pf = max(dep_anchors)
            dates[key] = {"ps": pf, "pf": pf}
            changed = True

    return dates


def compute_milestones_for_site_actual(
    row: Dict,
    db: Session,
    skipped_keys: set | None = None,
    user_expected_days_overrides: dict | None = None,
) -> tuple[List[Dict], Optional[date]]:
    """
    Actual-view milestone computation.

    Uses pj_p_4225_construction_start_finish as the known CX start date,
    then works backward through the dependency chain to compute expected
    (planned) dates for each milestone. Status is determined by comparing
    actual dates against these backward-computed expected dates.
    """
    today = date.today()

    milestones_config = get_milestones(db)
    milestones_config = apply_user_expected_days(milestones_config, user_expected_days_overrides or {})
    prereq_tails = get_prereq_tails(db)

    cx_start_date = parse_date(row.get("pj_p_4225_construction_start_finish"))
    if cx_start_date is None:
        return [], None

    dates = _compute_planned_dates_backward(
        cx_start_date, milestones_config, prereq_tails, skipped_keys=skipped_keys,
    )

    skipped = skipped_keys or set()
    preceding_map, following_map = _build_dependency_maps(milestones_config, skipped_keys=skipped)
    milestones = []

    for ms in milestones_config:
        key = ms["key"]
        if key not in dates:
            continue
        ps = dates[key]["ps"]
        pf = dates[key]["pf"]

        preceding = preceding_map.get(key, [])
        following = following_map.get(key, [])

        if key in skipped:
            continue

        actual, is_text, text_val, skip = _get_actual_date(row, ms)

        back_days = (cx_start_date - pf).days if pf else None

        if skip:
            row_out = _build_milestone_row(
                key, ms, ps, pf,
                actual=actual, status="On Track", delay=0,
                days_since=None, days_remaining=None,
                is_text=False, text_val=None,
                preceding=preceding, following=following,
            )
            row_out["back_days"] = back_days
            milestones.append(row_out)
            continue

        status, delay = compute_status(actual, pf, today, is_text, text_val)
        days_since = (today - actual).days if actual else None
        days_remaining = (pf - today).days if (actual is None and pf) else None

        row_out = _build_milestone_row(
            key, ms, ps, pf,
            actual=actual, status=status, delay=delay,
            days_since=days_since, days_remaining=days_remaining,
            is_text=is_text, text_val=text_val,
            preceding=preceding, following=following,
        )
        row_out["back_days"] = back_days
        milestones.append(row_out)

    return milestones, cx_start_date


def _build_dependency_maps(milestones_config: List[Dict], skipped_keys: set | None = None) -> tuple[Dict, Dict]:
    """
    Build preceding and following milestone name maps from the dependency graph.

    When *skipped_keys* is provided, skipped milestones are resolved through:
    if A → B(skipped) → C, then C's preceding shows A and A's following shows C.

    Returns:
        preceding_map: {key: [names of milestones this key depends on]}
        following_map: {key: [names of milestones that depend on this key]}
    """
    name_lookup = {m["key"]: m["name"] for m in milestones_config}
    skipped = skipped_keys or set()

    # Build raw dependency graph by key
    raw_preceding: Dict[str, List[str]] = {}
    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]
        if dep is None:
            raw_preceding[key] = []
        else:
            raw_preceding[key] = dep if isinstance(dep, list) else [dep]

    # Resolve preceding: walk through skipped predecessors to non-skipped ancestors
    def _resolve(key: str, visited: set | None = None) -> List[str]:
        if visited is None:
            visited = set()
        result = []
        for p in raw_preceding.get(key, []):
            if p in visited:
                continue
            visited.add(p)
            if p in skipped:
                result.extend(_resolve(p, visited))
            else:
                result.append(p)
        return result

    preceding_map: Dict[str, List[str]] = {}
    for ms in milestones_config:
        key = ms["key"]
        if key in skipped:
            preceding_map[key] = []
        else:
            preceding_map[key] = [name_lookup.get(k, k) for k in _resolve(key)]

    # Build following as reverse of resolved preceding
    following_map: Dict[str, List[str]] = {m["key"]: [] for m in milestones_config}
    for ms in milestones_config:
        key = ms["key"]
        if key in skipped:
            continue
        for p in _resolve(key):
            if p not in skipped and p in following_map:
                following_map[p].append(name_lookup.get(key, key))

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


def compute_forecasted_cx_start_only(
    row: Dict,
    milestones_config: List[Dict],
    prereq_tails: List[Dict],
    cx_start_offset_days: int,
    planned_start_col: str,
    skipped_keys: set | None = None,
) -> Optional[date]:
    """
    Lightweight version — computes only the forecasted_cx_start date for a row
    without building full milestone response dicts or computing statuses.
    Used for fast date-range filtering before the full computation.
    """
    origin_date = parse_date(row.get(planned_start_col))
    if origin_date is None:
        return None

    dates = _compute_planned_dates(origin_date, milestones_config, skipped_keys=skipped_keys, row=row)

    skipped = skipped_keys or set()

    # Build child→parents map for walking up the dependency chain
    child_to_parents: Dict[str, List[str]] = {}
    for ms in milestones_config:
        dep = ms["depends_on"]
        if dep is None:
            child_to_parents[ms["key"]] = []
        elif isinstance(dep, list):
            child_to_parents[ms["key"]] = dep
        else:
            child_to_parents[ms["key"]] = [dep]

    tail_dates = []
    for tail in prereq_tails:
        key = tail["key"]
        offset = tail["offset_days"]

        if key not in skipped:
            if key in dates:
                tail_dates.append(dates[key]["pf"] + timedelta(days=offset))
        else:
            queue = list(child_to_parents.get(key, []))
            visited = {key}
            while queue:
                ancestor = queue.pop(0)
                if ancestor in visited:
                    continue
                visited.add(ancestor)
                if ancestor in skipped:
                    queue.extend(child_to_parents.get(ancestor, []))
                else:
                    if ancestor in dates:
                        tail_dates.append(dates[ancestor]["pf"] + timedelta(days=offset))

    if not tail_dates:
        return None

    all_prereq_complete = max(tail_dates)
    return all_prereq_complete + timedelta(days=cx_start_offset_days)


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

    dates = _compute_planned_dates(origin_date, milestones_config, skipped_keys=skipped_keys, row=row)

    skipped = skipped_keys or set()
    preceding_map, following_map = _build_dependency_maps(milestones_config, skipped_keys=skipped)
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
