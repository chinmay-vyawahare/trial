"""
CX Actual Construction Summary service.

Queries sites where pj_a_4225_construction_start_finish IS NOT NULL
(actual construction has started). Defaults to current-month-start .. today.
Groups results by ISO week/year.
"""

from collections import defaultdict
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import STAGING_TABLE


def _build_where(
    region: str | None = None,
    market: str | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: str | None = None,
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

    if region:
        clauses.append("region = :region")
        params["region"] = region
    if market:
        clauses.append("m_market = :market")
        params["market"] = market
    if site_id:
        clauses.append("s_site_id = :site_id")
        params["site_id"] = site_id
    if vendor:
        clauses.append("construction_gc = :vendor")
        params["vendor"] = vendor
    if area:
        clauses.append("m_area = :area")
        params["area"] = area

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


def get_cx_actual_weekly_summary(
    db: Session,
    *,
    region: str | None = None,
    market: str | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: str | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """
    Return week-wise site counts grouped by ISO week/year
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

    # Group by ISO week
    weekly: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        raw_date = row.pj_a_4225_construction_start_finish
        if not raw_date:
            continue
        try:
            cx_date = date.fromisoformat(str(raw_date)[:10])
        except (ValueError, TypeError):
            continue

        iso = cx_date.isocalendar()
        key = (iso.year, iso.week)
        weekly[key].append({
            "site_id": row.s_site_id,
            "project_id": row.pj_project_id,
            "project_name": row.pj_project_name,
            "region": row.region,
            "market": row.m_market,
            "area": row.m_area,
            "vendor": row.construction_gc,
            "cx_actual_date": str(cx_date),
        })

    # Sort by year, week
    result = []
    for (year, week), sites in sorted(weekly.items()):
        week_start = date.fromisocalendar(year, week, 1)
        week_end = date.fromisocalendar(year, week, 7)
        result.append({
            "week": week,
            "year": year,
            "week_start": str(week_start),
            "week_end": str(week_end),
            "total": len(sites),
            "sites": sites,
        })

    return result, start_date, end_date
