from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy.orm import Session
from .queries import build_gantt_query
from .logic import compute_milestones_for_site, compute_overall_status, compute_status, _get_actual_date, _match_count_threshold, is_site_blocked
from .milestones import get_milestones, get_all_actual_columns, get_planned_start_column, get_milestone_thresholds, get_overall_thresholds, apply_user_expected_days, get_history_expected_days_overrides, get_history_expected_days_by_user, save_user_history_expected_days
from .utils import parse_date

def _apply_pace_constraint(
    sites: list[dict],
    config_db: Session,
    pace_constraint_flag: bool,
    user_id: str
) -> list[dict]:
    """
    Apply pace constraints to sites for a specific user_id:
        1. Only consider sites matching constraint geo (market/area/region).
        2. Use constraint start/end dates, or fallback to week_start/week_end.
        3. Exclude extra sites if more than max_sites.
        4. Pull from future weeks if fewer than max_sites.
    """
    from app.models.prerequisite import PaceConstraint

    if not pace_constraint_flag:
        return sites

    # --------------------------------
    # Fetch constraints only for this user
    # --------------------------------
    constraints = config_db.query(PaceConstraint).filter(
        PaceConstraint.user_id == user_id
    ).all()

    if not constraints:
        return sites

    # --------------------------------
    # Preprocess sites: parse forecast date & normalize geo
    # --------------------------------
    for site in sites:
        forecast = site.get("forecasted_cx_start_date")
        try:
            site["_forecast_date"] = date.fromisoformat(str(forecast)) if forecast else None
        except Exception:
            site["_forecast_date"] = None

        site["excluded_due_to_pace_constraint"] = False
        site.setdefault("note", "")

        site["_market"] = (site.get("market") or "").strip().lower()
        site["_area"] = (site.get("area") or "").strip().lower()
        site["_region"] = (site.get("region") or "").strip().lower()

    excluded_indices: set[int] = set()

    # --------------------------------
    # Helper: week boundaries
    # --------------------------------
    def next_week_start():
        today = date.today()
        return today - timedelta(days=today.weekday()) + timedelta(weeks=1)

    def next_week_end():
        return next_week_start() + timedelta(days=6)

    for c in constraints:
        # Use constraint dates if available, else fallback to week
        ws = c.start_date.date() if getattr(c, "start_date", None) else next_week_start()
        we = c.end_date.date() if getattr(c, "end_date", None) else next_week_end()

        c_market = (c.market or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_region = (c.region or "").strip().lower()

        matching_indices: list[int] = []
        future_indices: list[int] = []

        # --------------------------------
        # Collect matching + future sites
        # --------------------------------
        for idx, site in enumerate(sites):
            fd = site.get("_forecast_date")
            if not fd:
                continue

            # Skip if geo doesn't match constraint
            if c_market and site["_market"] != c_market:
                continue
            if c_area and site["_area"] != c_area:
                continue
            if c_region and site["_region"] != c_region:
                continue

            # Within constraint window
            if ws <= fd <= we:
                matching_indices.append(idx)
            elif fd > we:
                future_indices.append(idx)

        # --------------------------------
        # CASE 1: Too many → exclude extra
        # --------------------------------
        if len(matching_indices) > c.max_sites:

            sorted_indices = sorted(
                matching_indices,
                key=lambda i: abs((sites[i]["_forecast_date"] - ws).days)
            )

            keep = set(sorted_indices[:c.max_sites])

            for i in matching_indices:
                if i not in keep:
                    excluded_indices.add(i)

        # --------------------------------
        # CASE 2: Too few → pull from future
        # --------------------------------
        elif len(matching_indices) < c.max_sites:
            needed = c.max_sites - len(matching_indices)

            sorted_future = sorted(
                future_indices,
                key=lambda i: (sites[i]["_forecast_date"] - we).days
            )

            for i in sorted_future[:needed]:
                sites[i]["note"] = "considered future weeks sites to fulfill the pace"

    # --------------------------------
    # Final tagging
    # --------------------------------
    for idx, site in enumerate(sites):
        if idx in excluded_indices:
            site["excluded_due_to_pace_constraint"] = True
            site["exclude_reason"] = "Excluded - Pace Constraint"
        else:
            site["excluded_due_to_pace_constraint"] = False

        # Cleanup temporary fields
        site.pop("_forecast_date", None)
        site.pop("_market", None)
        site.pop("_area", None)
        site.pop("_region", None)

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
            site["exclude_reason"] = "Excluded - Crew Shortage"
        else:
            site["excluded_due_to_crew_shortage"] = False

    return sites


def get_all_sites_gantt(
    db: Session,
    config_db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
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

        # ── Reschedule logic when forecasted_cx_start is in the past ──
        note = None
        today = date.today()
        if forecasted_cx_start and forecasted_cx_start < today:
            # Check non-virtual milestones for missing actual_finish
            missing = [
                m for m in countable
                if not m.get("actual_finish")
            ]
            if not missing:
                # All milestones have actual_finish → ready for schedule
                forecasted_cx_start = today + timedelta(days=7)
                note = "Ready for schedule"
            else:
                # At least one milestone missing actual_finish
                # Pick the earliest (min sort_order) milestone without actual_finish
                missing_sorted = sorted(missing, key=lambda m: m.get("sort_order", 999))
                blocker = missing_sorted[0]
                delay_days = (today - forecasted_cx_start).days
                forecasted_cx_start = today + timedelta(days=7)
                note = f"Delayed due to {blocker['name']} by {delay_days} days"

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
                "note": note,
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

    # Apply pace constraints for user if enabled
    if pace_constraint_flag and user_id:
        sites = _apply_pace_constraint(sites, config_db, pace_constraint_flag, user_id)
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


def _normalize_geo_filter(value) -> list[str]:
    """Normalize a geo filter value (str, list, or None) to a list of lowercase strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip().lower()]
    return [v.strip().lower() for v in value if v]


def _get_pace_constraint(config_db: Session, user_id: str | None, region=None, area=None, market=None) -> list[dict]:
    """
    Fetch pace constraints for a user that match the geo filters.

    Returns a list of constraint dicts with region, area, market, max_sites.
    """
    if not user_id:
        return []

    from app.models.prerequisite import PaceConstraint

    constraints = (
        config_db.query(PaceConstraint)
        .filter(PaceConstraint.user_id == user_id)
        .all()
    )
    if not constraints:
        return []

    f_regions = _normalize_geo_filter(region)
    f_areas = _normalize_geo_filter(area)
    f_markets = _normalize_geo_filter(market)

    result = []
    for c in constraints:
        c_region = (c.region or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_market = (c.market or "").strip().lower()

        # Match: constraint geo must align with the filter geo
        if c_region:
            if f_regions and c_region not in f_regions:
                continue
        if c_area:
            if f_areas and c_area not in f_areas:
                continue
        if c_market:
            if f_markets and c_market not in f_markets:
                continue

        result.append({
            "region": c.region,
            "area": c.area,
            "market": c.market,
            "max_sites": c.max_sites,
        })

    return result


def get_dashboard_summary(
    db: Session,
    config_db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    status: str | None = None,
    user_id: str | None = None,
):
    """Dashboard summary using the same query and logic as the gantt chart."""
    sites, total_count, _ = get_all_sites_gantt(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
    )

    result = _get_pace_constraint(config_db, user_id, region=region, area=area, market=market)
    print(result,"Result")
    pace_max = sum(item.get("max_sites", 0) for item in (result or []))
    print(pace_max,"Pace Max")
    empty = {
        "dashboard_status": "ON TRACK",
        "on_track_pct": 0,
        "total_sites": 0,
        "in_progress_sites": 0,
        "critical_sites": 0,
        "on_track_sites": 0,
        "blocked_sites": 0,
        "excluded_crew_shortage_sites": 0,
        "excluded_pace_constraint_sites": 0,
        "pace_constraint_max_sites": pace_max,
    }
    
    if not sites:
        return empty

    # Applying the pace constraint
    if pace_constraint_flag:
        sites = _apply_pace_constraint(sites, config_db, pace_constraint_flag, user_id)
    else:
        for site in sites:
            site["excluded_due_to_pace_constraint"] = False

    def site_matches_constraint(site, constraints):
        def norm(val):
            return (val or "").strip().lower()

        s_region = norm(site.get("region"))
        s_area = norm(site.get("area"))
        s_market = norm(site.get("market"))

        for c in constraints:
            if (
                (not c.get("region") or norm(c.get("region")) == s_region) and
                (not c.get("area") or norm(c.get("area")) == s_area) and
                (not c.get("market") or norm(c.get("market")) == s_market)
            ):
                return True
        return False

    if result:
        sites = [s for s in sites if site_matches_constraint(s, result)]

    # Apply status filter if provided
    if status:
        sites = [s for s in sites if s.get("overall_status") == status]

    total = len(sites)
    if total == 0:
        return empty

    blocked = sum(1 for s in sites if s["overall_status"] == "Blocked")
    excluded_crew = sum(1 for s in sites if s.get("exclude_reason") == "Excluded - Crew Shortage")
    excluded_pace = sum(1 for s in sites if s.get("exclude_reason") == "Excluded - Pace Constraint")

    # Count statuses excluding blocked
    countable = [s for s in sites if s["overall_status"] not in ("Blocked")]
    on_track = sum(1 for s in countable if s["overall_status"] == "ON TRACK")
    in_progress = sum(1 for s in countable if s["overall_status"] == "IN PROGRESS")
    critical = sum(1 for s in countable if s["overall_status"] == "CRITICAL")

    non_blocked_total = len(countable)
    on_track_pct = (on_track / non_blocked_total * 100) if non_blocked_total > 0 else 0

    overall_thresholds = get_overall_thresholds(config_db)
    if overall_thresholds:
        dashboard_status, _ = _match_count_threshold(on_track, overall_thresholds)
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
        "excluded_crew_shortage_sites": excluded_crew,
        "excluded_pace_constraint_sites": excluded_pace,
        "pace_constraint_max_sites": pace_max,
    }


def get_history_gantt(
    db: Session,
    config_db: Session,
    date_from: date,
    date_to: date,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
):
    """
    Gantt chart using history-based SLA.

    Computes history_expected_days from the given date range, saves them
    per-user into user_history_expected_days, then runs the gantt
    logic using those values as expected_days overrides.
    """
    from app.services.sla_history import compute_history_expected_days
    from app.models.prerequisite import UserHistoryExpectedDays

    # Compute history-based expected_days from actual dates
    history_results = compute_history_expected_days(
        db, config_db, date_from, date_to,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
    )

    # Build overrides dict.
    # In history mode, ALL milestones use computed history values.
    # If no historical data exists (None), use 0 — never fall back to defaults.
    history_overrides = {}
    for item in history_results:
        computed = item["history_expected_days"]
        effective = computed if computed is not None else 0
        history_overrides[item["milestone_key"]] = effective

    # Save per-user history expected days
    if user_id:
        save_user_history_expected_days(config_db, user_id, history_results, date_from, date_to)

    # Get the latest updated_at timestamp for this user's history SLA
    from sqlalchemy import func as sa_func
    last_updated_row = None
    if user_id:
        last_updated_row = (
            config_db.query(sa_func.max(UserHistoryExpectedDays.updated_at))
            .filter(UserHistoryExpectedDays.user_id == user_id)
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
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
    )

    return sites, total_count, count, sla_last_updated
