from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy.orm import Session
from .queries import build_gantt_query, build_dashboard_query
from .logic import compute_milestones_for_site, compute_overall_status, compute_status, _get_actual_date, _match_pct_threshold, is_site_blocked
from .milestones import get_milestones, get_all_actual_columns, get_planned_start_column, get_milestone_thresholds, get_overall_thresholds, apply_user_expected_days, get_history_expected_days_overrides
from .utils import parse_date

def _apply_pace_constraint(sites: list[dict], config_db: Session, pace_constraint_id: int) -> list[dict]:
    """
    Apply a single pace constraint by ID.

    For the constraint (start_date, end_date, market/area/region, max_sites):
      1. Find sites whose forecasted_cx_start_date falls in [start_date, end_date]
         and match the constraint's market/area/region filters.
      2. Sort those sites by proximity to start_date (nearest = highest priority).
      3. Keep top max_sites, mark the rest as excluded.
    """
    from app.models.prerequisite import PaceConstraint

    c = config_db.query(PaceConstraint).filter(PaceConstraint.id == pace_constraint_id).first()
    if not c:
        return sites

    c_start = c.start_date.date() if hasattr(c.start_date, "date") else c.start_date
    c_end = c.end_date.date() if hasattr(c.end_date, "date") else c.end_date
    c_market = (c.market or "").strip().lower()
    c_area = (c.area or "").strip().lower()
    c_region = (c.region or "").strip().lower()

    matching_indices: list[int] = []
    for idx, site in enumerate(sites):
        forecast = site.get("forecasted_cx_start_date")
        if not forecast:
            continue

        try:
            forecast_date = date.fromisoformat(str(forecast))
        except (ValueError, TypeError):
            continue

        # Check if forecast falls within constraint date range
        if not (c_start <= forecast_date <= c_end):
            continue

        # Check scope filters (case-insensitive, skip if constraint field is empty)
        site_market = (site.get("market") or "").strip().lower()
        site_area = (site.get("area") or "").strip().lower()
        site_region = (site.get("region") or "").strip().lower()

        if c_market and site_market != c_market:
            continue
        if c_area and site_area != c_area:
            continue
        if c_region and site_region != c_region:
            continue

        matching_indices.append(idx)

    excluded_indices: set[int] = set()
    if len(matching_indices) > c.max_sites:
        # Sort by proximity to start_date (nearest first = highest priority)
        def sort_key(i):
            try:
                fd = date.fromisoformat(str(sites[i].get("forecasted_cx_start_date")))
                return abs((fd - c_start).days)
            except (ValueError, TypeError):
                return 999999

        sorted_indices = sorted(matching_indices, key=sort_key)

        # Keep first max_sites, exclude the rest
        for i in sorted_indices[c.max_sites:]:
            excluded_indices.add(i)

    # Tag sites
    for idx, site in enumerate(sites):
        if idx in excluded_indices:
            site["excluded_due_to_pace_constraint"] = True
            site["overall_status"] = "Excluded - Pace Constraint"
        else:
            site["excluded_due_to_pace_constraint"] = False

    return sites


def _apply_vendor_capacity(sites: list[dict], db: Session) -> list[dict]:
    """
    Apply vendor capacity constraints from public.gc_capacity_market_trial table.

    For each vendor+market combination, if the vendor has more sites than their
    day_wise_gc_capacity, sort sites by forecasted_cx_start_date (earliest first)
    and mark excess sites with excluded_due_to_crew_shortage=True.
    Sites with earlier forecasted starts are prioritised (kept).
    """
    from app.models.prerequisite import GcCapacityMarketTrial

    # Load all capacity rules from public schema (pre-populated, read-only)
    capacity_rows = db.query(GcCapacityMarketTrial).all()
    if not capacity_rows:
        return sites

    # Build lookup: (gc_company_lower, market_lower) -> capacity
    cap_lookup = {}
    for r in capacity_rows:
        key = (r.gc_company.strip().lower(), r.market.strip().lower())
        cap_lookup[key] = r.day_wise_gc_capacity

    # Group sites by (vendor, market)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx, site in enumerate(sites):
        vendor_name = (site.get("vendor_name") or "").strip().lower()
        market_name = (site.get("market") or "").strip().lower()
        if vendor_name and market_name:
            groups[(vendor_name, market_name)].append(idx)

    # For each group, check capacity and mark excess sites
    excluded_indices = set()
    for (vendor_key, market_key), indices in groups.items():
        capacity = cap_lookup.get((vendor_key, market_key))
        if capacity is None or len(indices) <= capacity:
            continue

        # Sort indices by forecasted_cx_start_date ascending (earliest first = keep)
        # Sites without a forecast date go last (will be excluded first)
        def sort_key(i):
            d = sites[i].get("forecasted_cx_start_date")
            return d if d else "9999-12-31"

        sorted_indices = sorted(indices, key=sort_key)

        # Keep first `capacity` sites, exclude the rest
        for i in sorted_indices[capacity:]:
            excluded_indices.add(i)

    # Tag sites — excluded sites get a special overall_status
    for idx, site in enumerate(sites):
        if idx in excluded_indices:
            site["excluded_due_to_crew_shortage"] = True
            site["overall_status"] = "Excluded - Crew Shortage"
        else:
            site["excluded_due_to_crew_shortage"] = False

    return sites


def get_all_sites_gantt(
    db: Session,
    config_db: Session,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_id: int | None = None,
):
    # Load milestone config from config DB
    milestones_config = get_milestones(config_db)
    milestone_columns = get_all_actual_columns(milestones_config)
    planned_start_col = get_planned_start_column(config_db)
    ms_thresholds = get_milestone_thresholds(config_db)

    # Query staging data from staging DB
    query, params = build_gantt_query(
        milestone_columns=milestone_columns,
        planned_start_column=planned_start_col,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
    )
    result = db.execute(query, params)
    rows = [dict(r._mapping) for r in result]

    sites = []
    total_count = 0
    count = 0
    if rows:
        total_count = rows[0]["total_count"]
        count = len(rows)

    for row in rows:
        milestones, forecasted_cx_start = compute_milestones_for_site(
            row, config_db, skipped_keys=skipped_keys,
            user_expected_days_overrides=user_expected_days_overrides,
        )
        if not milestones:
            continue

        # Exclude virtual milestones from status counting (skipped are already omitted)
        countable = [m for m in milestones if not m.get("is_virtual", False)]
        total = len(countable)
        on_track_count = sum(1 for m in countable if m["status"] == "On Track")
        in_progress_count = sum(1 for m in countable if m["status"] == "In Progress")
        delayed_count = sum(1 for m in countable if m["status"] == "Delayed")

        # Check if site is blocked (delay comments or delay code present)
        blocked = is_site_blocked(row)
        if blocked:
            overall = "Blocked"
            on_track_pct = 0
        else:
            overall = compute_overall_status(on_track_count, total, ms_thresholds)
            on_track_pct = round((on_track_count / total * 100), 2) if total > 0 else 0

        sites.append(
            {
                "vendor_name": row.get("construction_gc") or "",
                "site_id": row["s_site_id"],
                "project_id": row["pj_project_id"],
                "project_name": row["pj_project_name"],
                "market": row["m_market"],
                "area": row.get("m_area") or "",
                "region": row.get("region") or "",
                "delay_comments": row.get("pj_construction_start_delay_comments") or "",
                "delay_code": row.get("pj_construction_complete_delay_code") or "",
                "forecasted_cx_start_date": (
                    str(forecasted_cx_start) if forecasted_cx_start else None
                ),
                "milestones": [
                    {k: v for k, v in m.items() if k != "is_virtual"}
                    for m in milestones
                ],
                "overall_status": overall,
                "on_track_pct": on_track_pct,
                "milestone_status_summary": {
                    "total": total,
                    "on_track": on_track_count,
                    "in_progress": in_progress_count,
                    "delayed": delayed_count,
                },
            }
        )

    # Apply vendor capacity constraints if requested
    if consider_vendor_capacity:
        sites = _apply_vendor_capacity(sites, db)
    else:
        for site in sites:
            site["excluded_due_to_crew_shortage"] = False

    # Apply a single pace constraint if selected
    if pace_constraint_id:
        sites = _apply_pace_constraint(sites, config_db, pace_constraint_id)
    else:
        for site in sites:
            site["excluded_due_to_pace_constraint"] = False

    # Sort by forecasted_cx_start_date descending (latest first, nulls at bottom)
    sites.sort(
        key=lambda s: s.get("forecasted_cx_start_date") or "",
        reverse=True,
    )

    return sites, total_count, count

def _site_status(row, milestones_config, planned_start_col, ms_thresholds, skipped_keys, user_expected_days_overrides=None):
    """Compute overall status for one row — only dates, no full milestone dicts."""
    # Blocked sites get their own status — excluded from on_track/in_progress/critical counts
    if is_site_blocked(row):
        return "BLOCKED"

    origin_date = parse_date(row.get(planned_start_col))
    if origin_date is None:
        return None

    today = date.today()
    skipped = skipped_keys or set()
    overrides = user_expected_days_overrides or {}
    expected_by_key = {
        m["key"]: overrides.get(m["key"], m["expected_days"])
        for m in milestones_config
    }

    # Compute planned finish dates
    dates = {}
    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]
        gap = ms.get("start_gap_days", 1)

        if key in skipped:
            expected = 0
        elif dep is not None and isinstance(dep, list) and len(dep) > 1:
            expected = max(expected_by_key.get(d, 0) for d in dep)
        else:
            expected = expected_by_key.get(key, ms["expected_days"])

        if dep is None:
            pf = origin_date + timedelta(days=expected) if expected > 0 else origin_date
            dates[key] = pf
            continue

        dep_list = dep if isinstance(dep, list) else [dep]
        dep_finishes = [dates[d] for d in dep_list if d in dates]
        if not dep_finishes:
            continue
        ps = max(dep_finishes) + timedelta(days=gap)
        dates[key] = ps + timedelta(days=expected)

    # Count on-track milestones (exclude user-skipped from counting entirely)
    on_track = 0
    total = 0
    for ms in milestones_config:
        key = ms["key"]
        if key not in dates:
            continue

        if key in skipped:
            continue  # exclude skipped milestones from counting

        total += 1

        actual, is_text, text_val, skip_flag = _get_actual_date(row, ms)
        if skip_flag:
            on_track += 1
            continue

        status, _ = compute_status(actual, dates[key], today, is_text, text_val)
        if status == "On Track":
            on_track += 1

    if total == 0:
        return None
    return compute_overall_status(on_track, total, ms_thresholds)


def get_dashboard_summary(
    db: Session,
    config_db: Session,
    region: str = None,
    market: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
):
    # Load config once
    milestones_config = get_milestones(config_db)
    milestones_config = apply_user_expected_days(milestones_config, user_expected_days_overrides or {})
    milestone_columns = get_all_actual_columns(milestones_config)
    planned_start_col = get_planned_start_column(config_db)
    ms_thresholds = get_milestone_thresholds(config_db)
    overall_thresholds = get_overall_thresholds(config_db)

    # Lightweight query — only date cols needed for status calc
    query, params = build_dashboard_query(
        milestone_columns=milestone_columns,
        planned_start_column=planned_start_col,
        region=region,
        market=market,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
    )
    rows = [dict(r._mapping) for r in db.execute(query, params)]

    empty = {
        "dashboard_status": "ON TRACK",
        "on_track_pct": 0,
        "total_sites": 0,
        "in_progress_sites": 0,
        "critical_sites": 0,
        "on_track_sites": 0,
        "blocked_sites": 0,
    }
    if not rows:
        return empty

    # Compute per-site status
    statuses = []
    for row in rows:
        status = _site_status(row, milestones_config, planned_start_col, ms_thresholds, skipped_keys, user_expected_days_overrides)
        if status is not None:
            statuses.append(status)

    total = len(statuses)
    if total == 0:
        return empty

    blocked = sum(1 for s in statuses if s == "BLOCKED")
    # Exclude blocked sites from percentage calculations
    non_blocked_statuses = [s for s in statuses if s != "BLOCKED"]
    on_track = sum(1 for s in non_blocked_statuses if s == "ON TRACK")
    in_progress = sum(1 for s in non_blocked_statuses if s == "IN PROGRESS")
    critical = sum(1 for s in non_blocked_statuses if s == "CRITICAL")

    non_blocked_total = len(non_blocked_statuses)
    on_track_pct = (on_track / non_blocked_total * 100) if non_blocked_total > 0 else 0
    if overall_thresholds:
        dashboard_status, _ = _match_pct_threshold(on_track_pct, overall_thresholds)
    elif on_track_pct >= 60:
        dashboard_status = "ON TRACK"
    elif on_track_pct >= 30:
        dashboard_status = "IN PROGRESS"
    else:
        dashboard_status = "CRITICAL"

    return {
        "dashboard_status": dashboard_status,
        "on_track_pct": round(on_track_pct, 2),
        "total_sites": total,
        "in_progress_sites": in_progress,
        "critical_sites": critical,
        "on_track_sites": on_track,
        "blocked_sites": blocked,
    }


def get_history_gantt(
    db: Session,
    config_db: Session,
    date_from: date,
    date_to: date,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_id: int | None = None,
):
    """
    Gantt chart using history-based SLA.

    Computes history_expected_days from the given date range, saves them
    into milestone_definitions.history_expected_days, then runs the gantt
    logic using those values as expected_days overrides.
    """
    # Import here to avoid circular import (sla_history → gantt.milestones → gantt.service)
    from app.services.sla_history import compute_history_expected_days
    from app.models.prerequisite import MilestoneDefinition

    # Compute history-based expected_days from actual dates
    history_results = compute_history_expected_days(db, config_db, date_from, date_to)

    # Build overrides dict and save to DB.
    # In history mode, ALL milestones use computed history values.
    # If no historical data exists (None), use 0 — never fall back to defaults.
    history_overrides = {}
    for item in history_results:
        computed = item["history_expected_days"]
        effective = computed if computed is not None else 0
        history_overrides[item["milestone_key"]] = effective

        # Save/update in milestone_definitions
        ms_def = (
            config_db.query(MilestoneDefinition)
            .filter(MilestoneDefinition.key == item["milestone_key"])
            .first()
        )
        if ms_def:
            ms_def.history_expected_days = effective

    config_db.commit()

    # Get the latest updated_at timestamp for history SLA
    from sqlalchemy import func as sa_func
    last_updated_row = (
        config_db.query(sa_func.max(MilestoneDefinition.updated_at))
        .filter(MilestoneDefinition.history_expected_days.isnot(None))
        .scalar()
    )
    sla_last_updated = str(last_updated_row) if last_updated_row else None

    # Reuse the standard gantt function with history overrides
    sites, total_count, count = get_all_sites_gantt(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=history_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_id=pace_constraint_id,
    )

    return sites, total_count, count, sla_last_updated
