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


def _apply_actual_override(ms: Dict, override_value):
    """
    Build the same 4-tuple `_get_actual_date` returns, but from a user-uploaded
    override value. The shape of `override_value` depends on ms column_config.type:
      - single / max    : ISO date string
      - text            : free-text string
      - with_status     : {"date": "YYYY-MM-DD" | None, "status": "A"|"N"|...|""}
    """
    cfg = ms.get("column_config") or {}
    cfg_type = cfg.get("type", "single")

    if cfg_type in ("single", "max"):
        d = parse_date(
            override_value.get("date") if isinstance(override_value, dict) else override_value
        )
        return d, False, None, False

    if cfg_type == "text":
        val = override_value if isinstance(override_value, str) else ""
        return None, True, val, False

    if cfg_type == "with_status":
        if isinstance(override_value, dict):
            actual_date = parse_date(override_value.get("date"))
            status_val = (override_value.get("status") or "").strip()
        else:
            actual_date = parse_date(override_value)
            status_val = ""
        skip_values = cfg.get("skip", [])
        use_date_values = cfg.get("use_date", [])
        if status_val in skip_values or (not status_val and "" in skip_values):
            return actual_date, False, None, True
        if status_val in use_date_values:
            return actual_date, False, None, False
        return None, False, None, False

    return None, False, None, False


def _compute_planned_dates(
    origin_date: date,
    milestones: List[Dict],
    skipped_keys: set | None = None,
    row: Dict | None = None,
    planned_finish_overrides: Dict[str, date] | None = None,
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

    When *planned_finish_overrides* contains a milestone key, that milestone's
    pf is replaced with the override date and ps is pulled back to
    pf - expected_days (duration preserved). Downstream milestones anchor on
    the overridden pf via the existing dep_anchors logic, so the shift
    cascades through the dependency chain automatically.

    Overrides are applied only to upcoming milestones — when a milestone's
    originally-computed pf is already in the past (< today), the override is
    skipped and the baseline pf/ps is kept. Past milestones are historical
    record and are not moved retroactively.
    """
    skipped = skipped_keys or set()
    dates = {}
    overrides = planned_finish_overrides or {}
    today = date.today()
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
            ps = origin_date
            pf = origin_date + timedelta(days=expected) if expected > 0 else origin_date
            override = overrides.get(key)
            if override is not None and pf >= today:
                pf = override
                ps = pf - timedelta(days=expected) if expected > 0 else pf
            dates[key] = {"ps": ps, "pf": pf}
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

        override = overrides.get(key)
        if override is not None and pf >= today:
            pf = override
            ps = pf - timedelta(days=expected) if expected > 0 else pf

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
        # When a tail is admin-skipped, its tail buffer (offset_days) disappears
        # — the skip removes the pre-CX buffer entirely. The milestone's own
        # expected_days still propagates up to its parent through the walk
        # below, so the parent becomes the new right-most anchor at
        #   parent.pf = cx − skipped_tail.expected_days
        effective_offset = 0 if tail_key in skipped else offset
        pf = cx_start_date - timedelta(days=effective_offset)
        expected = ms["expected_days"]
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


def _compute_planned_dates_backward_from_db(
    cx_start_date: date,
    milestones: List[Dict],
    skipped_keys: set | None,
    user_back_days_overrides: dict | None,
) -> Dict[str, Dict]:
    """
    Fast path for the actual (right-to-left) view.

    Reads each milestone's effective `back_days` from:
      1. user override (if present)
      2. ms['back_days']  (the seeded / persisted value on MilestoneDefinition)
    and anchors the planned finish at `cx_start_date - back_days`.

    Skipped milestones are excluded from the result, matching the slow-path
    behaviour in `_compute_planned_dates_backward` + the caller's filter.
    """
    skipped = skipped_keys or set()
    overrides = user_back_days_overrides or {}
    dates: Dict[str, Dict] = {}
    for ms in milestones:
        key = ms["key"]
        if key in skipped:
            continue
        bd = overrides.get(key, ms.get("back_days"))
        if bd is None:
            continue
        pf = cx_start_date - timedelta(days=bd)
        expected = ms.get("expected_days") or 0
        ps = pf - timedelta(days=expected) if expected > 0 else pf
        dates[key] = {"ps": ps, "pf": pf}
    return dates


def _apply_pf_overrides_actual(
    dates: Dict[str, Dict],
    milestones_config: List[Dict],
    row: Dict,
    overrides: Dict[str, date],
    skipped_keys: set | None,
) -> tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Post-pass for actual view: apply user-uploaded planned_finish overrides
    on top of the baseline backward-computed *dates*.

    Behaviour:
      - For each milestone in topological order, inherit the max delta from
        its immediate parents (cascade through dep DAG).
      - If the milestone already has a staging actual_finish, the cascade
        stops here (delta = 0) — reality wins over commitment.
      - If the milestone has its own override, set its delta so that
        shifted_pf = override (composes with inherited parent delta).
      - Apply non-zero deltas: pf += delta, ps += delta. Duration preserved.

    Returns (mutated *dates*, override_source map {key: milestone_name}).
    """
    if not overrides:
        return dates, {}

    skipped = skipped_keys or set()

    # Build "has staging actual" set — used as the cascade-stop gate
    has_actual: set[str] = set()
    for ms in milestones_config:
        actual, is_text, text_val, skip = _get_actual_date(row, ms)
        if (actual is not None and not is_text) or skip:
            has_actual.add(ms["key"])

    # Walk in topological (sort_order) order: predecessors before dependents.
    cumulative_delta: Dict[str, int] = {k: 0 for k in dates}
    override_source: Dict[str, str] = {}

    for ms in milestones_config:
        key = ms["key"]
        if key not in dates or key in skipped:
            continue

        # Stop cascade at staging actuals — reality beats commitment.
        if key in has_actual:
            cumulative_delta[key] = 0
            continue

        # Inherit max delta across immediate parents.
        dep = ms.get("depends_on")
        dep_list = [] if dep is None else (dep if isinstance(dep, list) else [dep])
        parent_delta = max(
            (cumulative_delta.get(d, 0) for d in dep_list if d in cumulative_delta),
            default=0,
        )

        # Own override (if present) is absolute: shifted_pf must equal override.
        if key in overrides:
            shifted_baseline_pf = dates[key]["pf"] + timedelta(days=parent_delta)
            own_delta = (overrides[key] - shifted_baseline_pf).days
            cumulative_delta[key] = parent_delta + own_delta
            override_source[key] = ms.get("name", key)
        else:
            cumulative_delta[key] = parent_delta

    # Apply accumulated shifts.
    for k, d_ in cumulative_delta.items():
        if d_ == 0 or k not in dates:
            continue
        dates[k]["pf"] += timedelta(days=d_)
        dates[k]["ps"] += timedelta(days=d_)

    return dates, override_source


def compute_milestones_for_site_actual(
    row: Dict,
    db: Session,
    skipped_keys: set | None = None,
    user_expected_days_overrides: dict | None = None,
    user_back_days_overrides: dict | None = None,
    cx_override: date | None = None,
    planned_finish_overrides: Dict[str, date] | None = None,
) -> tuple[List[Dict], Optional[date]]:
    """
    Actual-view milestone computation.

    Uses pj_p_4225_construction_start_finish as the known CX start date
    (or cx_override if passed, so the orchestrator can feed a pace-adjusted
    CX that already accounts for vendor/pace constraints), then works
    backward through the dependency chain to compute expected (planned)
    dates for each milestone. Status is determined by comparing actual
    dates against these backward-computed expected dates.
    """
    today = date.today()

    milestones_config = get_milestones(db)
    milestones_config = apply_user_expected_days(milestones_config, user_expected_days_overrides or {})
    prereq_tails = get_prereq_tails(db)

    cx_start_date = cx_override or parse_date(row.get("pj_p_4225_construction_start_finish"))
    if cx_start_date is None:
        return [], None

    # Fast path: read persisted back_days from MilestoneDefinition.back_days
    # (seeded + maintained by admin mutation hooks) and apply any per-key
    # user pin from `user_back_days_overrides`.
    #
    # Slow path (BFS) is used when:
    #   - the user has expected_days overrides (those shift ancestors'
    #     back_days; the persisted column doesn't account for them), or
    #   - any non-skipped milestone is missing a persisted back_days value
    #     (fresh install / freshly-added milestone before global persist).
    has_all_back_days = all(
        ms.get("back_days") is not None
        for ms in milestones_config
        if ms["key"] not in (skipped_keys or set())
    )
    if has_all_back_days and not user_expected_days_overrides:
        dates = _compute_planned_dates_backward_from_db(
            cx_start_date, milestones_config, skipped_keys, user_back_days_overrides,
        )
    else:
        dates = _compute_planned_dates_backward(
            cx_start_date, milestones_config, prereq_tails, skipped_keys=skipped_keys,
        )
        # Apply user back_days pins on top of slow-path output (single-milestone
        # overrides — they don't propagate to ancestors).
        if user_back_days_overrides:
            for k, bd in user_back_days_overrides.items():
                if k in dates:
                    pf = cx_start_date - timedelta(days=bd)
                    expected = next(
                        (m.get("expected_days") or 0 for m in milestones_config if m["key"] == k),
                        0,
                    )
                    ps = pf - timedelta(days=expected) if expected > 0 else pf
                    dates[k] = {"ps": ps, "pf": pf}

    # Apply user-uploaded planned_finish overrides + cascade to descendants.
    # Cascade stops at any descendant that already has a staging actual_finish.
    if planned_finish_overrides:
        dates, _override_source = _apply_pf_overrides_actual(
            dates, milestones_config, row, planned_finish_overrides, skipped_keys,
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
    planned_finish_overrides: Dict[str, date] | None = None,
) -> Optional[date]:
    """
    Lightweight version — computes only the forecasted_cx_start date for a row
    without building full milestone response dicts or computing statuses.
    Used for fast date-range filtering before the full computation.
    """
    origin_date = parse_date(row.get(planned_start_col))
    if origin_date is None:
        return None

    dates = _compute_planned_dates(
        origin_date, milestones_config,
        skipped_keys=skipped_keys, row=row,
        planned_finish_overrides=planned_finish_overrides,
    )

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
    planned_finish_overrides: Dict[str, date] | None = None,
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

    dates = _compute_planned_dates(
        origin_date, milestones_config,
        skipped_keys=skipped_keys, row=row,
        planned_finish_overrides=planned_finish_overrides,
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
