"""
Export service — converts gantt chart data into a CSV file.

Reuses the existing get_all_sites_gantt() to fetch data, then flattens
each site + its milestones into CSV rows.

Two formats are supported:
  - "flat": one row per site, milestones as columns
  - (default) "flat" is the only format for now
"""

import csv
import io
import json
from sqlalchemy.orm import Session

from app.models.prerequisite import UserFilter, MilestoneDefinition
from app.services.gantt import get_all_sites_gantt
from app.services.gantt.service import get_history_gantt
from app.services.gantt.milestones import get_user_expected_days_overrides


def _get_user_filters(config_db: Session, user_id: str) -> dict:
    """Load saved filters for a user. Returns dict of filter values."""
    row = config_db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
    if not row:
        return {}

    result = {
        "region": row.region,
        "market": row.market,
        "vendor": row.vendor,
        "site_id": row.site_id,
        "area": row.area,
        "plan_type_include": None,
        "regional_dev_initiatives": row.regional_dev_initiatives,
    }
    if row.plan_type_include:
        try:
            result["plan_type_include"] = json.loads(row.plan_type_include)
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def _get_skipped_keys(config_db: Session) -> set[str]:
    """Return globally skipped milestone keys."""
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


def export_gantt_csv(
    db: Session,
    config_db: Session,
    user_id: str | None = None,
    region: str | None = None,
    market: str | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: str | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    status: str | None = None,
) -> str:
    """
    Build a CSV string of the full gantt chart.

    If user_id is provided, applies that user's saved filters (merged with explicit params).
    Otherwise exports all sites with no filters.

    Returns the CSV content as a string.
    """
    # Resolve saved filters (gate-checks like plan_type, dev_initiatives)
    filters = {}
    user_ed_overrides = {}
    if user_id:
        filters = _get_user_filters(config_db, user_id)
        user_ed_overrides = get_user_expected_days_overrides(config_db, user_id)

    skipped_keys = _get_skipped_keys(config_db)

    # Explicit params override saved filters
    final_region = region or filters.get("region")
    final_market = market or filters.get("market")
    final_site_id = site_id or filters.get("site_id")
    final_vendor = vendor or filters.get("vendor")
    final_area = area or filters.get("area")

    # Fetch all gantt data (no pagination — full export)
    sites, total_count, count = get_all_sites_gantt(
        db,
        config_db,
        region=final_region,
        market=final_market,
        site_id=final_site_id,
        vendor=final_vendor,
        area=final_area,
        plan_type_include=filters.get("plan_type_include"),
        regional_dev_initiatives=filters.get("regional_dev_initiatives"),
        limit=None,
        offset=None,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_ed_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
    )

    # Post-filter by status if requested
    if status:
        status_upper = status.upper()
        sites = [
            s for s in sites
            if (s.get("overall_status") or "").upper() == status_upper
            or (s.get("exclude_reason") or "").upper() == status_upper
        ]

    if not sites:
        # Return CSV with just headers
        return _build_csv([], [])

    # Collect all unique milestone names across all sites for column headers
    # Skip virtual milestones (All Prerequisites Complete, Cx Start Forecast)
    _VIRTUAL_KEYS = {"all_prereq", "cx_start_forecast"}
    milestone_names = []
    seen = set()
    for site in sites:
        for ms in site.get("milestones", []):
            key = ms.get("key", "")
            name = ms.get("name", "")
            if name and name not in seen and key not in _VIRTUAL_KEYS:
                milestone_names.append(name)
                seen.add(name)

    return _build_csv(sites, milestone_names)


def _build_csv(sites: list[dict], milestone_names: list[str]) -> str:
    """
    Build the CSV string with all fields from the gantt response.

    Site-level columns:
      Site ID, Project ID, Project Name, Market, Area, Region, Vendor,
      Forecasted CX Start, Overall Status, On Track %,
      Total Milestones, On Track, In Progress, Delayed

    Per-milestone columns (for each milestone):
      Status, Planned Start, Planned Finish, Actual Finish,
      Expected Days, Delay Days, Task Owner, Phase Type
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Build header — site-level fields
    header = [
        "Site ID",
        "Project ID",
        "Project Name",
        "Market",
        "Area",
        "Region",
        "Vendor",
        "All Prerequisites Complete Date",
        "Forecasted CX Start",
        "Overall Status",
        "On Track %",
        "Total Milestones",
        "On Track",
        "In Progress",
        "Delayed",
        "Note",
        "Exclude Reason",
        "Delay Comments",
        "Delay Code",
    ]

    # Per-milestone columns (8 columns per milestone)
    for name in milestone_names:
        header.append(f"{name} - Status")
        header.append(f"{name} - Planned Start")
        header.append(f"{name} - Planned Finish")
        header.append(f"{name} - Actual Finish")
        header.append(f"{name} - Expected Days")
        header.append(f"{name} - Delay Days")
        header.append(f"{name} - Task Owner")
        header.append(f"{name} - Phase Type")

    writer.writerow(header)

    # Write rows
    for site in sites:
        ms_by_name = {}
        all_prereq_date = ""
        for ms in site.get("milestones", []):
            ms_by_name[ms.get("name", "")] = ms
            if ms.get("key") == "all_prereq":
                all_prereq_date = ms.get("planned_finish", "")

        summary = site.get("milestone_status_summary", {})

        row = [
            site.get("site_id", ""),
            site.get("project_id", ""),
            site.get("project_name", ""),
            site.get("market", ""),
            site.get("area", ""),
            site.get("region", ""),
            site.get("vendor_name", ""),
            all_prereq_date,
            site.get("forecasted_cx_start_date", ""),
            site.get("overall_status", ""),
            site.get("on_track_pct", ""),
            summary.get("total", ""),
            summary.get("on_track", ""),
            summary.get("in_progress", ""),
            summary.get("delayed", ""),
            site.get("note", "") or "",
            site.get("exclude_reason", "") or "",
            site.get("delay_comments", "") or "",
            site.get("delay_code", "") or "",
        ]

        # Add all milestone fields
        for name in milestone_names:
            ms = ms_by_name.get(name, {})
            row.append(ms.get("status", ""))
            row.append(ms.get("planned_start", ""))
            row.append(ms.get("planned_finish", ""))
            row.append(ms.get("actual_finish", ""))
            row.append(ms.get("expected_days", ""))
            row.append(ms.get("delay_days", ""))
            row.append(ms.get("task_owner", "") or "")
            row.append(ms.get("phase_type", "") or "")

        writer.writerow(row)

    return output.getvalue()


def export_gantt_csv_history(
    db: Session,
    config_db: Session,
    date_from,
    date_to,
    user_id: str | None = None,
    region: str | None = None,
    market: str | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: str | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    status: str | None = None,
) -> str:
    """
    Build a CSV string of the gantt chart using SLA history-based expected_days.

    Uses history-based expected_days computed from [date_from, date_to].
    """
    filters = {}
    if user_id:
        filters = _get_user_filters(config_db, user_id)

    skipped_keys = _get_skipped_keys(config_db)

    final_region = region or filters.get("region")
    final_market = market or filters.get("market")
    final_site_id = site_id or filters.get("site_id")
    final_vendor = vendor or filters.get("vendor")
    final_area = area or filters.get("area")

    sites, total_count, count, _sla_last_updated = get_history_gantt(
        db=db,
        config_db=config_db,
        date_from=date_from,
        date_to=date_to,
        region=final_region,
        market=final_market,
        site_id=final_site_id,
        vendor=final_vendor,
        area=final_area,
        plan_type_include=filters.get("plan_type_include"),
        regional_dev_initiatives=filters.get("regional_dev_initiatives"),
        limit=None,
        offset=None,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
    )

    # Post-filter by status if requested
    if status:
        status_upper = status.upper()
        sites = [
            s for s in sites
            if (s.get("overall_status") or "").upper() == status_upper
            or (s.get("exclude_reason") or "").upper() == status_upper
        ]

    if not sites:
        return _build_csv([], [])

    _VIRTUAL_KEYS = {"all_prereq", "cx_start_forecast"}
    milestone_names = []
    seen = set()
    for site in sites:
        for ms in site.get("milestones", []):
            key = ms.get("key", "")
            name = ms.get("name", "")
            if name and name not in seen and key not in _VIRTUAL_KEYS:
                milestone_names.append(name)
                seen.add(name)

    return _build_csv(sites, milestone_names)
