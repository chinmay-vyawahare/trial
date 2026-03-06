from datetime import date, timedelta
from sqlalchemy.orm import Session
from .queries import build_gantt_query, build_dashboard_query
from .logic import compute_milestones_for_site, compute_overall_status, compute_status, _get_actual_date, _match_pct_threshold, is_site_blocked
from .milestones import get_milestones, get_all_actual_columns, get_planned_start_column, get_milestone_thresholds, get_overall_thresholds, apply_user_expected_days, get_history_expected_days_overrides
from .utils import parse_date

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

    # Build overrides dict and save to DB
    history_overrides = {}
    for item in history_results:
        if item["history_expected_days"] is None:
            continue
        history_overrides[item["milestone_key"]] = item["history_expected_days"]

        # Save/update in milestone_definitions
        ms_def = (
            config_db.query(MilestoneDefinition)
            .filter(MilestoneDefinition.key == item["milestone_key"])
            .first()
        )
        if ms_def:
            ms_def.history_expected_days = item["history_expected_days"]

    config_db.commit()

    # Reuse the standard gantt function with history overrides
    return get_all_sites_gantt(
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
    )
