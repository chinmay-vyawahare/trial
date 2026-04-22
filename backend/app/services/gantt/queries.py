from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import STAGING_TABLE
from app.core.filters import apply_geo_filters


def build_gantt_query(
    milestone_columns: list[str],
    planned_start_column: str,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    view_type: str = "forecast",
    site_id_filter: list[str] | None = None,
):
    where_clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
    ]

    if view_type == "actual":
        where_clauses.append("pj_p_4225_construction_start_finish IS NOT NULL")

    params = {}

    # --- Gate check: por_plan_type IN (include selected values) ---
    if plan_type_include:
        placeholders = ", ".join(f":pti_{i}" for i in range(len(plan_type_include)))
        where_clauses.append(f"COALESCE(por_plan_type, '') IN ({placeholders})")
        for i, val in enumerate(plan_type_include):
            params[f"pti_{i}"] = val

    # --- Gate check: por_regional_dev_initiatives ILIKE ---
    if regional_dev_initiatives:
        where_clauses.append("COALESCE(por_regional_dev_initiatives, '') ILIKE :rdi_pattern")
        params["rdi_pattern"] = f"%{regional_dev_initiatives}%"

    apply_geo_filters(
        where_clauses, params,
        region=region, market=market, area=area,
        site_id=site_id, vendor=vendor,
    )

    # Explicit site_id restriction for two-phase actual flow (Stage 4 heavy fetch).
    if site_id_filter:
        placeholders = ", ".join(f":sid_{i}" for i in range(len(site_id_filter)))
        where_clauses.append(f"s_site_id IN ({placeholders})")
        for i, sid in enumerate(site_id_filter):
            params[f"sid_{i}"] = sid

    where_sql = " AND ".join(where_clauses)

    pagination_sql = ""
    if limit is not None:
        pagination_sql += f" LIMIT {int(limit)}"
    if offset is not None:
        pagination_sql += f" OFFSET {int(offset)}"

    # Fixed columns always needed
    fixed_columns = [
        "s_site_id",
        "pj_project_id",
        "pj_project_name",
        "m_market",
        "m_area",
        "smp_name",
        "region",
        planned_start_column,
        "construction_gc",
        "pj_construction_start_delay_comments",
        "pj_construction_complete_delay_code",
    ]

    # Combine fixed + milestone actual columns (deduplicated, preserving order)
    all_columns = list(fixed_columns)
    seen = set(fixed_columns)
    for col in milestone_columns:
        if col not in seen:
            all_columns.append(col)
            seen.add(col)

    columns_sql = ",\n            ".join(all_columns)

    query = text(
        f"""
    WITH filtered_records AS (
        SELECT DISTINCT ON (pj_project_id, s_site_id)
            {columns_sql}
        FROM {STAGING_TABLE}
        WHERE {where_sql}
        ORDER BY pj_project_id, s_site_id
    )
    SELECT *, COUNT(*) OVER () AS total_count
    FROM filtered_records
    ORDER BY s_site_id
    {pagination_sql}
    """
    )
    return query, params


def build_light_cx_query(
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
):
    """
    Lightweight query for the actual-view two-phase flow: returns only the
    columns needed to run vendor/pace constraints (site_id, vendor, market,
    area, region, forecasted_cx_start_date) without pulling milestone dates.

    Applies the SAME filters as build_gantt_query(view_type="actual"), so the
    survivor list is a valid input to the heavy query in stage 4.
    """
    where_clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
        "pj_p_4225_construction_start_finish IS NOT NULL",
    ]
    params = {}

    if plan_type_include:
        placeholders = ", ".join(f":pti_{i}" for i in range(len(plan_type_include)))
        where_clauses.append(f"COALESCE(por_plan_type, '') IN ({placeholders})")
        for i, val in enumerate(plan_type_include):
            params[f"pti_{i}"] = val

    if regional_dev_initiatives:
        where_clauses.append("COALESCE(por_regional_dev_initiatives, '') ILIKE :rdi_pattern")
        params["rdi_pattern"] = f"%{regional_dev_initiatives}%"

    apply_geo_filters(
        where_clauses, params,
        region=region, market=market, area=area,
        site_id=site_id, vendor=vendor,
    )

    where_sql = " AND ".join(where_clauses)

    # Actual view anchors to pj_p_4225 (the planned CX start), not the root
    # milestone column used in forecast view.
    query = text(f"""
        SELECT DISTINCT ON (pj_project_id, s_site_id)
            s_site_id,
            pj_project_id,
            construction_gc AS vendor_name,
            m_market AS market,
            m_area AS area,
            region,
            pj_p_4225_construction_start_finish::date AS forecasted_cx_start_date
        FROM {STAGING_TABLE}
        WHERE {where_sql}
        ORDER BY pj_project_id, s_site_id
    """)
    return query, params


def build_dashboard_query(
    milestone_columns: list[str],
    planned_start_column: str,
    region: list[str] | None = None,
    market: list[str] | None = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
):
    """Lightweight query for dashboard — only date columns needed for status calc."""
    where_clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
    ]
    params = {}

    if plan_type_include:
        placeholders = ", ".join(f":pti_{i}" for i in range(len(plan_type_include)))
        where_clauses.append(f"COALESCE(por_plan_type, '') IN ({placeholders})")
        for i, val in enumerate(plan_type_include):
            params[f"pti_{i}"] = val

    if regional_dev_initiatives:
        where_clauses.append("COALESCE(por_regional_dev_initiatives, '') ILIKE :rdi_pattern")
        params["rdi_pattern"] = f"%{regional_dev_initiatives}%"

    apply_geo_filters(
        where_clauses, params,
        region=region, market=market, area=area,
        vendor=vendor,
    )

    where_sql = " AND ".join(where_clauses)

    # Only fetch: planned_start + milestone date cols + delay columns
    fixed_columns = [
        planned_start_column,
        "pj_construction_start_delay_comments",
        "pj_construction_complete_delay_code",
    ]

    all_columns = list(fixed_columns)
    seen = set(fixed_columns)
    for col in milestone_columns:
        if col not in seen:
            all_columns.append(col)
            seen.add(col)

    columns_sql = ",\n            ".join(all_columns)

    query = text(
        f"""
    SELECT
        {columns_sql}
    FROM {STAGING_TABLE}
    WHERE {where_sql}
    """
    )
    return query, params


def get_geo_hierarchy(db: Session, project_type: str = "macro") -> list[dict]:
    """Return distinct region → area → market mappings from the staging table."""
    base_where, params = _build_base_where(project_type)
    q = text(
        f"""
        SELECT DISTINCT region, m_area, m_market
        FROM {STAGING_TABLE}
        WHERE {base_where}
          AND region IS NOT NULL
          AND m_area IS NOT NULL
          AND m_market IS NOT NULL
        ORDER BY region, m_area, m_market
        """
    )
    rows = db.execute(q, params)
    return [{"region": r[0], "area": r[1], "market": r[2]} for r in rows]


def _build_base_where(project_type: str = "macro"):
    """Build the base WHERE clause for filter options based on project_type."""
    if project_type == "ahloa":
        clauses = [
            "pj_hard_cost_vendor_assignment_po ILIKE '%NOKIA%'",
            "por_release_version = 'Radio Upgrade NR'",
            "por_plan_added_date > '2025-03-28'",
            "pj_a_4225_construction_start_finish IS NULL",
        ]
    else:
        clauses = [
            "smp_name = 'NTM'",
            "COALESCE(TRIM(construction_gc), '') != ''",
            "pj_a_4225_construction_start_finish IS NULL",
        ]
    return " AND ".join(clauses), {}


def _build_hierarchy_optimized(rows):
    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))

    for region, area, market, vendor in rows:
        tree[region][area][market].add(vendor)

    result = []

    for region, areas in tree.items():
        region_obj = {
            "region": region,
            "areas": []
        }

        region_areas = region_obj["areas"]

        for area, markets in areas.items():
            area_obj = {
                "area": area,
                "markets": []
            }

            area_markets = area_obj["markets"]

            for market, vendors in markets.items():
                area_markets.append({
                    "market": market,
                    "vendors": [{"vendor": v} for v in sorted(vendors)]
                })

            region_areas.append(area_obj)

        result.append(region_obj)

    return result


def get_region_hierarchy(db: Session, region: str = None, area: str = None, market: str = None, project_type: str = "macro"):
    base_where, params = _build_base_where(project_type)

    # build filters dynamically
    filters = {
        "region": region,
        "m_area": area,
        "m_market": market,
    }

    clauses = []

    for col, value in filters.items():
        if value:
            clauses.append(f"{col} = :{col}")
            params[col] = value

    where_clause = base_where
    if clauses:
        where_clause += " AND " + " AND ".join(clauses)

    query = text(f"""
        SELECT
            region,
            m_area,
            m_market,
            construction_gc
        FROM {STAGING_TABLE}
        WHERE {where_clause}
            AND region IS NOT NULL
            AND m_area IS NOT NULL
            AND m_market IS NOT NULL
            AND construction_gc IS NOT NULL
    """)

    rows = db.execute(query, params).fetchall()

    return _build_hierarchy_optimized(rows)


def get_filter_options(db: Session, project_type: str = "macro"):
    """Get all distinct filter values: regions, markets, areas, site_ids, vendors."""
    base_where, params = _build_base_where(project_type)

    regions_q = text(
        f"""
        SELECT DISTINCT region FROM {STAGING_TABLE}
        WHERE {base_where} AND region IS NOT NULL
        ORDER BY region
        """
    )
    markets_q = text(
        f"""
        SELECT DISTINCT m_market FROM {STAGING_TABLE}
        WHERE {base_where} AND m_market IS NOT NULL
        ORDER BY m_market
        """
    )
    areas_q = text(
        f"""
        SELECT DISTINCT m_area FROM {STAGING_TABLE}
        WHERE {base_where} AND m_area IS NOT NULL
        ORDER BY m_area
        """
    )
    sites_q = text(
        f"""
        SELECT DISTINCT s_site_id FROM {STAGING_TABLE}
        WHERE {base_where} AND s_site_id IS NOT NULL
        ORDER BY s_site_id
        """
    )
    vendors_q = text(
        f"""
        SELECT DISTINCT construction_gc FROM {STAGING_TABLE}
        WHERE {base_where} AND construction_gc IS NOT NULL
        ORDER BY construction_gc
        """
    )

    regions = [r[0] for r in db.execute(regions_q, params)]
    markets = [r[0] for r in db.execute(markets_q, params)]
    areas = [r[0] for r in db.execute(areas_q, params)]
    site_ids = [r[0] for r in db.execute(sites_q, params)]
    vendors = [r[0] for r in db.execute(vendors_q, params)]

    return {
        "regions": regions,
        "markets": markets,
        "areas": areas,
        "site_ids": site_ids,
        "vendors": vendors,
    }
