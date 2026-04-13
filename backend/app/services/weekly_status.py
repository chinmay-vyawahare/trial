"""
Weekly status aggregation service.

Groups sites by ISO week/year based on forecasted_cx_start_date,
then counts overall_status values per week.
"""

from collections import defaultdict
from datetime import date
from sqlalchemy.orm import Session
from app.services.gantt import get_all_sites_gantt


def get_weekly_status_counts(
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
    user_id: str | None = None,
    status: str | None = None,
    strict_pace_apply: bool = False,
    view_type: str = "forecast",
) -> list[dict]:
    """
    Return weekly status counts grouped by ISO week/year, with region breakdown.

    Each entry:
      {
        "week": 10,
        "year": 2026,
        "week_start": "2026-03-02",
        "week_end": "2026-03-08",
        "total": 5,
        "status_counts": {
          "EAST": {
            "ON TRACK": 2,
            "IN PROGRESS": 1,
            "CRITICAL": 0,
            "Blocked": 0,
            "Excluded - Crew Shortage": 0,
            "Excluded - Pace Constraint": 0,
          },
          "WEST": {
            "ON TRACK": 0,
            "IN PROGRESS": 0,
            "CRITICAL": 1,
            "Blocked": 0,
            "Excluded - Crew Shortage": 0,
            "Excluded - Pace Constraint": 1,
          }
        }
      }
    """
    # Get all sites (no pagination limit)
    sites, _, _ = get_all_sites_gantt(
        db,
        config_db,
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
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    # Post-filter by status if requested
    if status:
        sites = [s for s in sites if (s.get("exclude_reason") or s.get("overall_status", "")).upper() == status.upper()]

    ALL_STATUSES = [
        "ON TRACK", "IN PROGRESS", "CRITICAL","Blocked", 
    ]

    # Group by (year, week) -> region -> status counts
    weekly = {}
    for site in sites:
        forecast = site.get("forecasted_cx_start_date")
        if not forecast:
            continue
        try:
            fd = date.fromisoformat(str(forecast))
        except (ValueError, TypeError):
            continue

        iso = fd.isocalendar()
        key = (iso.year, iso.week)

        region_name = site.get("Region") or site.get("region") or "Unknown"
        site_status = site.get("overall_status", "")

        if key not in weekly:
            weekly[key] = {}

        if region_name not in weekly[key]:
            weekly[key][region_name] = {s: 0 for s in ALL_STATUSES}

        if site_status not in weekly[key][region_name]:
            weekly[key][region_name][site_status] = 0

        weekly[key][region_name][site_status] += 1

    # Sort by year, week and build result
    result = []
    for (year, week), regional_counts in sorted(weekly.items()):
        # Compute the Monday of this ISO week
        try:
            week_start = date.fromisocalendar(year, week, 1)
            week_end = date.fromisocalendar(year, week, 7)
        except ValueError:
            continue  # skip invalid week

        # Safe total calculation
        total = sum(
            sum(status.values())
            for status in regional_counts.values()
            if isinstance(status, dict)
        )

        result.append({
            "week": week,
            "year": year,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total": total,
            "status_counts": regional_counts,
        })

    return result
