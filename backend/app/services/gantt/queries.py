from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import STAGING_TABLE


def build_gantt_query(
    milestone_columns: list[str],
    planned_start_column: str,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    area: str = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
):
    where_clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
    ]
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

    if region:
        where_clauses.append("region = :region")
        params["region"] = region
    if market:
        where_clauses.append("m_market = :market")
        params["market"] = market
    if site_id:
        where_clauses.append("s_site_id = :site_id")
        params["site_id"] = site_id
    if vendor:
        where_clauses.append("construction_gc = :vendor")
        params["vendor"] = vendor
    if area:
        where_clauses.append("m_area = :area")
        params["area"] = area

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


def build_dashboard_query(
    milestone_columns: list[str],
    planned_start_column: str,
    region: str = None,
    market: str = None,
    vendor: str = None,
    area: str = None,
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

    if region:
        where_clauses.append("region = :region")
        params["region"] = region
    if market:
        where_clauses.append("m_market = :market")
        params["market"] = market
    if vendor:
        where_clauses.append("construction_gc = :vendor")
        params["vendor"] = vendor
    if area:
        where_clauses.append("m_area = :area")
        params["area"] = area

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


def _build_base_where():
    """Build the base WHERE clause for filter options (always empty/constant)."""
    clauses = [
        "smp_name = 'NTM'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
    ]
    return " AND ".join(clauses), {}


def get_filter_options(db: Session):
    """Get all distinct filter values: regions, markets, areas, site_ids, vendors."""
    base_where, params = _build_base_where()

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
