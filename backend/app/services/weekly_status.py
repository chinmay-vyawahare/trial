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
) -> list[dict]:
    """
    Return weekly status counts grouped by ISO week/year.

    Each entry:
      {
        "week": 10,
        "year": 2026,
        "week_start": "2026-03-02",
        "total": 5,
        "status_counts": {
          "ON TRACK": 2,
          "IN PROGRESS": 1,
          "CRITICAL": 1,
          "Blocked": 0,
          "Excluded - Crew Shortage": 0,
          "Excluded - Pace Constraint": 1,
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
    )

    # Post-filter by status if requested
    if status:
        sites = [s for s in sites if s.get("overall_status", "").upper() == status.upper()]

    ALL_STATUSES = [
        "ON TRACK", "IN PROGRESS", "CRITICAL",
        "Blocked", "Excluded - Crew Shortage", "Excluded - Pace Constraint",
    ]

    # Group by (year, week)
    weekly: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: {s: 0 for s in ALL_STATUSES})
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
        site_status = site.get("overall_status", "")
        if site_status in weekly[key]:
            weekly[key][site_status] += 1
        else:
            weekly[key][site_status] = weekly[key].get(site_status, 0) + 1

    # Sort by year, week and build result
    result = []
    for (year, week), counts in sorted(weekly.items()):
        # Compute the Monday of this ISO week
        week_start = date.fromisocalendar(year, week, 1)
        week_end = date.fromisocalendar(year, week, 7)
        result.append({
            "week": week,
            "year": year,
            "week_start": str(week_start),
            "week_end": str(week_end),
            "total": sum(counts.values()),
            "status_counts": counts,
        })

    return result
