from datetime import date
from sqlalchemy.orm import Session

from app.services.gantt.queries import build_gantt_query
from app.services.gantt.logic import (
    compute_forecasted_cx_start_only,
    compute_milestones_for_site,
    compute_overall_status,
    is_site_blocked,
)
from app.services.gantt.milestones import (
    get_milestones,
    get_all_actual_columns,
    get_planned_start_column,
    get_milestone_thresholds,
    get_prereq_tails,
    get_cx_start_offset_days,
    apply_user_expected_days,
)
from app.services.gantt.service import _apply_vendor_capacity, _apply_pace_constraint


def _load_config(config_db: Session, user_expected_days_overrides: dict | None):
    """Load milestone config once for reuse across passes."""
    milestones_config = get_milestones(config_db)
    milestones_config = apply_user_expected_days(milestones_config, user_expected_days_overrides or {})
    milestone_columns = get_all_actual_columns(milestones_config)
    planned_start_col = get_planned_start_column(config_db)
    ms_thresholds = get_milestone_thresholds(config_db)
    prereq_tails = get_prereq_tails(config_db)
    cx_start_offset_days = get_cx_start_offset_days(config_db)
    return milestones_config, milestone_columns, planned_start_col, ms_thresholds, prereq_tails, cx_start_offset_days


def _fetch_rows(db, milestone_columns, planned_start_col, region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives):
    """Fetch all rows from staging (no pagination — we filter in Python by forecast date)."""
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
    )
    result = db.execute(query, params)
    return [dict(r._mapping) for r in result]


def _filter_rows_by_forecast(rows, milestones_config, prereq_tails, cx_start_offset_days, planned_start_col, skipped_keys, start_date, end_date):
    """
    Pass 1: Lightweight — compute only the forecasted_cx_start date for each row
    and keep only those within [start_date, end_date].
    """
    filtered = []
    for row in rows:
        forecast = compute_forecasted_cx_start_only(
            row, milestones_config, prereq_tails, cx_start_offset_days,
            planned_start_col, skipped_keys=skipped_keys,
        )
        if forecast and start_date <= forecast <= end_date:
            filtered.append(row)
    return filtered


def _build_sites(rows, config_db, ms_thresholds, skipped_keys, user_expected_days_overrides):
    """
    Pass 2: Full milestone computation only for pre-filtered rows.
    """
    sites = []
    for row in rows:
        milestones, forecasted_cx_start = compute_milestones_for_site(
            row, config_db, skipped_keys=skipped_keys,
            user_expected_days_overrides=user_expected_days_overrides,
        )
        if not milestones:
            continue

        countable = [m for m in milestones if not m.get("is_virtual", False)]
        total = len(countable)
        on_track_count = sum(1 for m in countable if m["status"] == "On Track")
        in_progress_count = sum(1 for m in countable if m["status"] == "In Progress")
        delayed_count = sum(1 for m in countable if m["status"] == "Delayed")

        blocked = is_site_blocked(row)
        if blocked:
            overall = "Blocked"
            on_track_pct = 0
        else:
            overall = compute_overall_status(on_track_count, total, ms_thresholds)
            on_track_pct = round((on_track_count / total * 100), 2) if total > 0 else 0

        sites.append({
            "vendor_name": row.get("construction_gc") or "",
            "site_id": row["s_site_id"],
            "project_id": row["pj_project_id"],
            "project_name": row["pj_project_name"],
            "market": row["m_market"],
            "area": row.get("m_area") or "",
            "region": row.get("region") or "",
            "delay_comments": row.get("pj_construction_start_delay_comments") or "",
            "delay_code": row.get("pj_construction_complete_delay_code") or "",
            "forecasted_cx_start_date": str(forecasted_cx_start) if forecasted_cx_start else None,
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
        })
    return sites


def _apply_post_filters(sites, db, config_db, consider_vendor_capacity, pace_constraint_flag, user_id, status):
    """Apply vendor capacity, pace constraint, and status filters."""
    if consider_vendor_capacity:
        sites = _apply_vendor_capacity(sites, db)
    else:
        for site in sites:
            site["excluded_due_to_crew_shortage"] = False

    if pace_constraint_flag and user_id:
        sites = _apply_pace_constraint(sites, config_db, pace_constraint_flag, user_id)
    else:
        for site in sites:
            site["excluded_due_to_pace_constraint"] = False

    if status:
        sites = [s for s in sites if (s.get("overall_status") or "").upper() == status.upper()]

    # Sort by forecasted_cx_start_date descending (latest first, nulls at bottom)
    sites.sort(key=lambda s: s.get("forecasted_cx_start_date") or "", reverse=True)

    return sites


def get_calendar_sites(
    db: Session,
    config_db: Session,
    start_date: date,
    end_date: date,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
    status: str | None = None,
):
    """
    Optimised calendar view — default SLA.

    Pass 1: lightweight forecast-only computation to filter rows by date range.
    Pass 2: full milestone computation only for matching rows.
    """
    config = _load_config(config_db, user_expected_days_overrides)
    milestones_config, milestone_columns, planned_start_col, ms_thresholds, prereq_tails, cx_start_offset_days = config

    # Fetch all rows matching geographic/gate filters (no pagination — calendar filters in Python)
    rows = _fetch_rows(db, milestone_columns, planned_start_col, region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives)

    # Pass 1: fast forecast date filter
    filtered_rows = _filter_rows_by_forecast(
        rows, milestones_config, prereq_tails, cx_start_offset_days,
        planned_start_col, skipped_keys, start_date, end_date,
    )

    # Pass 2: full computation only for rows in range
    sites = _build_sites(filtered_rows, config_db, ms_thresholds, skipped_keys, user_expected_days_overrides)

    sites = _apply_post_filters(sites, db, config_db, consider_vendor_capacity, pace_constraint_flag, user_id, status)

    return sites


def get_calendar_history_sites(
    db: Session,
    config_db: Session,
    start_date: date,
    end_date: date,
    sla_date_from: date,
    sla_date_to: date,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
    status: str | None = None,
):
    """
    Optimised calendar view — history-based SLA.

    Computes history_expected_days from [sla_date_from, sla_date_to], then:
    Pass 1: lightweight forecast-only computation to filter rows by date range.
    Pass 2: full milestone computation only for matching rows.
    """
    from app.services.sla_history import compute_history_expected_days
    from app.models.prerequisite import MilestoneDefinition
    from sqlalchemy import func as sa_func

    # Compute and save history-based expected_days
    history_results = compute_history_expected_days(db, config_db, sla_date_from, sla_date_to)
    history_overrides = {}
    for item in history_results:
        computed = item["history_expected_days"]
        effective = computed if computed is not None else 0
        history_overrides[item["milestone_key"]] = effective

        ms_def = (
            config_db.query(MilestoneDefinition)
            .filter(MilestoneDefinition.key == item["milestone_key"])
            .first()
        )
        if ms_def:
            ms_def.history_expected_days = effective

    config_db.commit()

    last_updated_row = (
        config_db.query(sa_func.max(MilestoneDefinition.updated_at))
        .filter(MilestoneDefinition.history_expected_days.isnot(None))
        .scalar()
    )
    sla_last_updated = str(last_updated_row) if last_updated_row else None

    # Load config with history overrides applied
    config = _load_config(config_db, history_overrides)
    milestones_config, milestone_columns, planned_start_col, ms_thresholds, prereq_tails, cx_start_offset_days = config

    # Fetch all rows matching geographic/gate filters
    rows = _fetch_rows(db, milestone_columns, planned_start_col, region, market, site_id, vendor, area, plan_type_include, regional_dev_initiatives)

    # Pass 1: fast forecast date filter
    filtered_rows = _filter_rows_by_forecast(
        rows, milestones_config, prereq_tails, cx_start_offset_days,
        planned_start_col, skipped_keys, start_date, end_date,
    )

    # Pass 2: full computation only for rows in range
    sites = _build_sites(filtered_rows, config_db, ms_thresholds, skipped_keys, history_overrides)

    sites = _apply_post_filters(sites, db, config_db, consider_vendor_capacity, pace_constraint_flag, user_id, status)

    return sites, sla_last_updated
