"""
Calendar Gantt service.

Wraps get_all_sites_gantt and get_history_gantt to support filtering
by a list of site_ids, then post-filters by status and date range.
"""

from datetime import date, datetime
from sqlalchemy.orm import Session
from app.services.gantt.service import get_all_sites_gantt, get_history_gantt


def get_calendar_gantt_sites(
    db: Session,
    config_db: Session,
    start_date: date,
    end_date: date,
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
    site_ids: list[str] | None = None,
):
    sites, total_count, count = get_all_sites_gantt(
        db,
        config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=None,
        offset=None,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        strict_pace_apply=strict_pace_apply,
    )

    if site_ids:
        site_ids_set = set(site_ids)
        sites = [s for s in sites if s.get("site_id") in site_ids_set]

    if status:
        sites = [s for s in sites if s.get("overall_status", "").upper() == status.upper()]

    filtered_sites = [
        site for site in sites
        if site.get("forecasted_cx_start_date")
        and start_date
        <= datetime.strptime(site["forecasted_cx_start_date"], "%Y-%m-%d").date()
        <= end_date
    ]

    return filtered_sites


def get_calendar_history_gantt_sites(
    db: Session,
    config_db: Session,
    start_date: date,
    end_date: date,
    sla_date_from: date,
    sla_date_to: date,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
    status: str | None = None,
    strict_pace_apply: bool = False,
    site_ids: list[str] | None = None,
):
    sites, total_count, count, sla_last_updated = get_history_gantt(
        db,
        config_db,
        date_from=sla_date_from,
        date_to=sla_date_to,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=None,
        offset=None,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        strict_pace_apply=strict_pace_apply,
    )

    if site_ids:
        site_ids_set = set(site_ids)
        sites = [s for s in sites if s.get("site_id") in site_ids_set]

    if status:
        sites = [s for s in sites if s.get("overall_status", "").upper() == status.upper()]

    filtered_sites = [
        site for site in sites
        if site.get("forecasted_cx_start_date")
        and start_date
        <= datetime.strptime(site["forecasted_cx_start_date"], "%Y-%m-%d").date()
        <= end_date
    ]

    return filtered_sites, sla_last_updated
