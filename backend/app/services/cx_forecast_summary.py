"""
CX Forecast Weekly Summary service.

Queries the staging table directly for pj_p_4225_construction_start_finish
(planned construction start date) and groups sites by ISO week/year.
Returns weekly site counts with geo/vendor breakdowns.
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
    """Build WHERE clauses and params dict for the CX forecast query."""
    clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
        "pj_p_4225_construction_start_finish IS NOT NULL",
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

    # Date range filter on the planned construction start
    if start_date:
        clauses.append("CAST(pj_p_4225_construction_start_finish AS DATE) >= :start_date")
        params["start_date"] = start_date
    if end_date:
        clauses.append("CAST(pj_p_4225_construction_start_finish AS DATE) <= :end_date")
        params["end_date"] = end_date

    return " AND ".join(clauses), params


def get_cx_forecast_weekly_summary(
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
    based on pj_p_4225_construction_start_finish.

    Each entry:
      {
        "week": 10, "year": 2026,
        "week_start": "2026-03-02", "week_end": "2026-03-08",
        "total": 12,
        "sites": [
          {
            "site_id": "SITE001",
            "project_id": "PRJ-101",
            "project_name": "Tower Build",
            "region": "Northeast",
            "market": "NYC",
            "area": "Area 1",
            "vendor": "Vendor A",
            "cx_start_date": "2026-03-04"
          }, ...
        ]
      }
    """
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
            pj_p_4225_construction_start_finish
        FROM {STAGING_TABLE}
        WHERE {where_sql}
        ORDER BY pj_project_id, s_site_id
    """)

    rows = db.execute(query, params).fetchall()

    # Group by ISO week
    weekly: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        raw_date = row.pj_p_4225_construction_start_finish
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
            "cx_start_date": str(cx_date),
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

    return result
