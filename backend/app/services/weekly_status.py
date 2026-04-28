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
    project_type: str = "macro",
    tab: str = "construction",
    user_skips: list | None = None,
) -> list[dict]:
    """
    Return weekly status counts grouped by ISO week/year, nested as
    region → area → market → status counts.

    Each entry:
      {
        "week": 10,
        "year": 2026,
        "week_start": "2026-03-02",
        "week_end": "2026-03-08",
        "total": 5,
        "status_counts": {
          "EAST": {
            "NY": {
              "New York": {
                "ON TRACK": 2, "IN PROGRESS": 1, "CRITICAL": 0, "Blocked": 0
              }
            }
          }
        }
      }
    """
    # Get all sites (no pagination limit)
    if project_type == "ahloa":
        if tab == "survey":
            from app.services.ahloa.gantt_ahloa_scope import get_ahloa_gantt_scope
            sites, _, _ = get_ahloa_gantt_scope(
                db=db, config_db=config_db,
                region=region, market=market, site_id=site_id,
                vendor=vendor, area=area,
                plan_type_include=plan_type_include,
                regional_dev_initiatives=regional_dev_initiatives,
                consider_vendor_capacity=consider_vendor_capacity,
                pace_constraint_flag=pace_constraint_flag,
                user_id=user_id, user_skips=user_skips,
            )
        else:
            from app.services.ahloa.gantt_ahloa_construction import get_ahloa_gantt
            sites, _, _ = get_ahloa_gantt(
                db=db, config_db=config_db,
                region=region, market=market, site_id=site_id,
                vendor=vendor, area=area,
                plan_type_include=plan_type_include,
                regional_dev_initiatives=regional_dev_initiatives,
                consider_vendor_capacity=consider_vendor_capacity,
                pace_constraint_flag=pace_constraint_flag,
                user_id=user_id, user_skips=user_skips,
            )
    else:
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

    # Group by (year, week) -> region -> area -> market -> status counts
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

        # Extract hierarchy
        region_name = site.get("Region") or site.get("region") or "Unknown"
        area_name = site.get("Area") or site.get("area") or "Unknown"
        market_name = site.get("Market") or site.get("market") or "Unknown"

        site_status = site.get("overall_status", "")

        # Initialize hierarchy
        if key not in weekly:
            weekly[key] = {}

        if region_name not in weekly[key]:
            weekly[key][region_name] = {}

        if area_name not in weekly[key][region_name]:
            weekly[key][region_name][area_name] = {}

        if market_name not in weekly[key][region_name][area_name]:
            weekly[key][region_name][area_name][market_name] = {
                s: 0 for s in ALL_STATUSES
            }

        if site_status not in weekly[key][region_name][area_name][market_name]:
            weekly[key][region_name][area_name][market_name][site_status] = 0

        weekly[key][region_name][area_name][market_name][site_status] += 1

    # Build result
    result = []

    for (year, week), regional_counts in sorted(weekly.items()):
        try:
            week_start = date.fromisocalendar(year, week, 1)
            week_end = date.fromisocalendar(year, week, 7)
        except ValueError:
            continue

        def recursive_sum(d):
            """Recursively sum all integers in a nested dict."""
            total = 0
            if isinstance(d, dict):
                for v in d.values():
                    total += recursive_sum(v)
            elif isinstance(d, int):
                total += d
            return total

        total = recursive_sum(regional_counts)

        result.append({
            "week": week,
            "year": year,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total": total,
            "status_counts": regional_counts,
        })

    return result
