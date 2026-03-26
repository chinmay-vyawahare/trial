"""
Analytics service — pending milestone counts with site counts.

Two modes:
1. Auto/User Override SLA  — uses get_all_sites_gantt with default or user-override expected_days
2. SLA History             — uses get_all_sites_gantt with history-based expected_days

All functions accept optional date_from / date_to parameters to restrict results
to sites whose forecasted_cx_start_date falls within the given range.

Blocked sites (overall_status == "Blocked") are excluded from all analytics
counts and returned separately as a blocked_sites count.
"""

from collections import defaultdict
from datetime import date
from sqlalchemy.orm import Session

# Virtual milestones are computed, not real prerequisites — exclude from analytics
VIRTUAL_MILESTONE_KEYS = {"all_prereq", "cx_start_forecast"}


def _is_countable(m: dict) -> bool:
    """Return True if the milestone should be counted in analytics (not virtual)."""
    return m.get("key", "") not in VIRTUAL_MILESTONE_KEYS


def _separate_blocked(sites: list[dict]) -> tuple[list[dict], int]:
    """Split sites into (active_sites, blocked_count). Blocked = overall_status is 'Blocked'."""
    active = []
    blocked = 0
    for site in sites:
        if (site.get("overall_status") or "").upper() == "BLOCKED":
            blocked += 1
        else:
            active.append(site)
    return active, blocked


def _count_pending_milestones(sites: list[dict], blocked_sites: int = 0) -> dict:
    """
    For each site, count pending milestones (those without actual_finish).
    Return a dict with total_sites, blocked_sites, and buckets.
    """
    pending_count_per_site: dict[str, int] = {}

    for site in sites:
        site_id = site.get("site_id", "")
        pending = 0
        for m in site.get("milestones", []):
            if _is_countable(m) and not m.get("actual_finish"):
                pending += 1
        pending_count_per_site[site_id] = pending

    # Group: how many sites have N pending milestones
    bucket: dict[int, int] = defaultdict(int)
    for count in pending_count_per_site.values():
        bucket[count] += 1

    # Determine total number of countable milestones from any site
    total_milestones = 0
    if sites:
        total_milestones = sum(1 for m in sites[0].get("milestones", []) if _is_countable(m))

    # Include 0 (completed) through total_milestones with 0-filled gaps
    buckets = [
        {"pending_milestone_count": i, "site_count": bucket.get(i, 0)}
        for i in range(0, total_milestones + 1)
    ]
    return {"total_sites": len(sites), "blocked_sites": blocked_sites, "buckets": buckets}


def _count_pending_by_milestone_name(sites: list[dict], blocked_sites: int = 0) -> dict:
    """
    For each milestone name, count how many sites have it pending (no actual_finish).
    Return dict with total_sites, blocked_sites, and milestones list sorted by sort_order.
    """
    # Track pending count and sort_order per milestone key
    pending: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    orders: dict[str, int] = {}

    for site in sites:
        for m in site.get("milestones", []):
            if not _is_countable(m):
                continue
            key = m.get("key", "")
            if key not in names:
                names[key] = m.get("name", key)
                orders[key] = m.get("sort_order", 999)
            if not m.get("actual_finish"):
                pending[key] += 1

    milestones = [
        {
            "milestone_key": k,
            "milestone_name": names[k],
            "pending_site_count": pending.get(k, 0),
            "sort_order": orders[k],
        }
        for k in names
    ]
    milestones.sort(key=lambda x: x["sort_order"])
    return {"total_sites": len(sites), "blocked_sites": blocked_sites, "milestones": milestones}


def _filter_sites_by_date_range(
    sites: list[dict],
    date_from: date | None,
    date_to: date | None,
) -> list[dict]:
    """Keep only sites whose forecasted_cx_start_date falls within [date_from, date_to]."""
    if not date_from and not date_to:
        return sites
    filtered = []
    for site in sites:
        raw = site.get("forecasted_cx_start_date")
        if not raw:
            continue
        try:
            forecast = date.fromisoformat(str(raw))
        except (ValueError, TypeError):
            continue
        if date_from and forecast < date_from:
            continue
        if date_to and forecast > date_to:
            continue
        filtered.append(site)
    return filtered


def _get_sites(
    db, config_db,
    region=None, market=None, site_id=None, vendor=None, area=None,
    plan_type_include=None, regional_dev_initiatives=None,
    skipped_keys=None, user_expected_days_overrides=None,
    consider_vendor_capacity=False, pace_constraint_flag=False, user_id=None,
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> tuple[list[dict], int]:
    """Return (active_sites, blocked_count) with blocked sites removed."""
    from app.services.gantt import get_all_sites_gantt
    sites, _, _ = get_all_sites_gantt(
        db, config_db,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
    )
    sites = _filter_sites_by_date_range(sites, filter_date_from, filter_date_to)
    return _separate_blocked(sites)


def _get_sites_history(
    db, config_db, date_from, date_to,
    region=None, market=None, site_id=None, vendor=None, area=None,
    plan_type_include=None, regional_dev_initiatives=None,
    skipped_keys=None, consider_vendor_capacity=False,
    pace_constraint_flag=False, user_id=None,
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> tuple[list[dict], int]:
    """Return (active_sites, blocked_count) with blocked sites removed."""
    from app.services.sla_history import compute_history_expected_days
    from app.services.gantt.milestones import save_user_history_expected_days
    history_results = compute_history_expected_days(
        db, config_db, date_from, date_to, use_median=True,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
    )
    history_overrides = {}
    for item in history_results:
        if item["history_expected_days"] is not None:
            history_overrides[item["milestone_key"]] = item["history_expected_days"]
    # Save per-user history expected days
    if user_id:
        save_user_history_expected_days(config_db, user_id, history_results, date_from, date_to)
    return _get_sites(
        db, config_db,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=history_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )


def get_pending_milestones_auto(
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> dict:
    """Pending milestone distribution using auto/user-override SLA."""
    sites, blocked = _get_sites(
        db, config_db,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _count_pending_milestones(sites, blocked)


def get_pending_milestones_history(
    db: Session,
    config_db: Session,
    date_from,
    date_to,
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> dict:
    """Pending milestone distribution using SLA history-based expected_days."""
    sites, blocked = _get_sites_history(
        db, config_db, date_from, date_to,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _count_pending_milestones(sites, blocked)


def get_pending_by_milestone_auto(
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> dict:
    """Per-milestone pending site count using auto/user-override SLA."""
    sites, blocked = _get_sites(
        db, config_db,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _count_pending_by_milestone_name(sites, blocked)


def get_pending_by_milestone_history(
    db: Session,
    config_db: Session,
    date_from,
    date_to,
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> dict:
    """Per-milestone pending site count using SLA history-based expected_days."""
    sites, blocked = _get_sites_history(
        db, config_db, date_from, date_to,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _count_pending_by_milestone_name(sites, blocked)


def _filter_drilldown(
    sites: list[dict],
    drilldown_type: str,
    pending_count: int | None,
    milestone_key: str | None,
) -> list[dict]:
    """
    Filter sites based on drilldown click:
    - drilldown_type="pending_count": sites with exactly `pending_count` pending milestones
    - drilldown_type="milestone_key": sites where the given milestone_key is pending
    """
    if drilldown_type == "pending_count" and pending_count is not None:
        result = []
        for site in sites:
            count = sum(1 for m in site.get("milestones", []) if _is_countable(m) and not m.get("actual_finish"))
            if count == pending_count:
                result.append(site)
        return result

    if drilldown_type == "milestone_key" and milestone_key:
        result = []
        for site in sites:
            for m in site.get("milestones", []):
                if m.get("key") == milestone_key and not m.get("actual_finish"):
                    result.append(site)
                    break
        return result

    return sites


def drilldown_sites_auto(
    db: Session,
    config_db: Session,
    drilldown_type: str,
    pending_count: int | None = None,
    milestone_key: str | None = None,
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> tuple[list[dict], int]:
    """Drilldown: return (filtered_sites, blocked_count)."""
    sites, blocked = _get_sites(
        db, config_db,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _filter_drilldown(sites, drilldown_type, pending_count, milestone_key), blocked


def drilldown_sites_history(
    db: Session,
    config_db: Session,
    date_from,
    date_to,
    drilldown_type: str,
    pending_count: int | None = None,
    milestone_key: str | None = None,
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
    filter_date_from: date | None = None,
    filter_date_to: date | None = None,
) -> tuple[list[dict], int]:
    """Drilldown: return (filtered_sites, blocked_count)."""
    sites, blocked = _get_sites_history(
        db, config_db, date_from, date_to,
        region=region, market=market, site_id=site_id, vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        filter_date_from=filter_date_from,
        filter_date_to=filter_date_to,
    )
    return _filter_drilldown(sites, drilldown_type, pending_count, milestone_key), blocked
