"""
CX Actual Construction Summary service.

Queries sites where pj_a_4225_construction_start_finish IS NOT NULL
(actual construction has started). Defaults to current-month-start .. today.
Groups results by day.
"""

from collections import defaultdict
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import STAGING_TABLE
from app.core.filters import apply_geo_filters


def _build_where(
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """Build WHERE clauses and params for actual construction query."""
    clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NOT NULL",
    ]
    params: dict = {}

    apply_geo_filters(
        clauses, params,
        region=region, market=market, area=area,
        site_id=site_id, vendor=vendor,
    )

    # Gate checks
    if plan_type_include:
        placeholders = ", ".join(f":pti_{i}" for i in range(len(plan_type_include)))
        clauses.append(f"COALESCE(por_plan_type, '') IN ({placeholders})")
        for i, val in enumerate(plan_type_include):
            params[f"pti_{i}"] = val
    if regional_dev_initiatives:
        clauses.append("COALESCE(por_regional_dev_initiatives, '') ILIKE :rdi_pattern")
        params["rdi_pattern"] = f"%{regional_dev_initiatives}%"

    # Date range on actual construction start (defaults applied in caller)
    if start_date:
        clauses.append("CAST(pj_a_4225_construction_start_finish AS DATE) >= :start_date")
        params["start_date"] = start_date
    if end_date:
        clauses.append("CAST(pj_a_4225_construction_start_finish AS DATE) <= :end_date")
        params["end_date"] = end_date

    return " AND ".join(clauses), params


def get_cx_actual_daily_summary(
    db: Session,
    *,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict], str, str]:
    """
    Return day-wise site counts grouped by date
    based on pj_a_4225_construction_start_finish (actual construction start).
    """
    # Default range: 1st of current month → today
    today = date.today()
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()

    where_sql, params = _build_where(
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        start_date=start_date, end_date=end_date,
    )

    query = text(f"""
        SELECT DISTINCT ON (pj_project_id, s_site_id)
            s_site_id,
            pj_project_id,
            pj_project_name,
            region,
            m_market,
            m_area,
            construction_gc,
            pj_a_4225_construction_start_finish
        FROM {STAGING_TABLE}
        WHERE {where_sql}
        ORDER BY pj_project_id, s_site_id
    """)

    rows = db.execute(query, params).fetchall()

    # Group by date
    daily: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        raw_date = row.pj_a_4225_construction_start_finish
        if not raw_date:
            continue
        try:
            cx_date = date.fromisoformat(str(raw_date)[:10])
        except (ValueError, TypeError):
            continue

        day_key = str(cx_date)
        daily[day_key].append({
            "site_id": row.s_site_id,
            "project_id": row.pj_project_id,
            "project_name": row.pj_project_name,
            "region": row.region,
            "market": row.m_market,
            "area": row.m_area,
            "vendor": row.construction_gc,
            "cx_actual_date": day_key,
        })

    # Sort by date
    result = []
    for day, sites in sorted(daily.items()):
        result.append({
            "date": day,
            "total": len(sites),
            "sites": sites,
        })

    return result, start_date, end_date
