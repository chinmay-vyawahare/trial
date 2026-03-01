from sqlalchemy import text
from sqlalchemy.orm import Session

def build_gantt_query(
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    limit: int = None,
    offset: int = None,
):
    where_clauses = [
        "smp_name = 'NTM'",
        "COALESCE(por_plan_type, '') NOT IN ('Equipment Upgrade', 'FOA')",
        "COALESCE(por_regional_dev_initiatives, '') ILIKE '%2026 Build Plan%'",
        "COALESCE(TRIM(construction_gc), '') != ''",
        "pj_a_4225_construction_start_finish IS NULL",
    ]
    params = {}

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

    where_sql = " AND ".join(where_clauses)

    pagination_sql = ""
    if limit is not None:
        pagination_sql += f" LIMIT {int(limit)}"
    if offset is not None:
        pagination_sql += f" OFFSET {int(offset)}"

    print("\n" + "=" * 50)
    print(f"DEBUG_UUID_GANTT: build_gantt_query CALLED")
    print(f"DEBUG_UUID_GANTT: limit={limit}, offset={offset}")
    print(f"DEBUG_UUID_GANTT: pagination_sql='{pagination_sql}'")
    print(f"DEBUG_UUID_GANTT: final_params={params}")
    print("=" * 50 + "\n")

    query = text(
        f"""
    WITH filtered_records AS (
        SELECT
            s_site_id AS site_id,
            pj_project_id AS project_id,
            pj_project_name AS project_name,
            m_market AS market,
            smp_name AS smp_name,
            region AS region,
            pj_p_3710_ran_entitlement_complete_finish AS p_3710_raw,
            pj_a_3710_ran_entitlement_complete_finish AS a_3710_raw,
            construction_gc AS a_gc_assignment,
            ms_1310_pre_construction_package_received_actual AS a_pre_ntp_raw,
            ms_1316_pre_con_site_walk_completed_actual AS a_site_walk_manual_raw,
            ms_1321_talon_view_drone_svcs_actual AS a_site_walk_drone_raw,
            ms_1323_ready_for_scoping_actual AS a_ready_scoping_raw,
            ms_1327_scoping_and_quoting_package_validated_actual AS a_scoping_validated_raw,
            ms_1331_scoping_package_submitted_actual AS a_quote_submitted_raw,
            pj_a_3850_bom_submitted_bom_in_bat_finish AS a_3850_raw,
            ms1555_construction_complete_so_header AS a_cpo_raw,
            pj_steel_received_date AS a_steel_date_raw,
            pj_steel_received_status AS a_steel_status,
            pj_a_3875_bom_received_bom_in_aims_finish AS a_3875_raw,
            pj_a_3925_msl_pickup_date_finish AS a_3925_raw,
            pj_a_4000_ll_ntp_received AS a_access_raw,
            ms_1407_tower_ntp_validated_actual AS a_ntp_raw,
            ms1555_construction_complete_spo_issued_date AS a_spo_raw,
            COUNT(*) OVER () AS total_count
        FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {where_sql}
    )
    SELECT * FROM filtered_records
    ORDER BY site_id
    {pagination_sql}
    """
    )
    return query, params

def get_filter_options(db: Session):
    """Get all distinct filter values: regions, markets, site_ids, and vendors."""
    base_where = """
        smp_name = 'NTM'
        AND COALESCE(por_plan_type, '') NOT IN ('Equipment Upgrade', 'FOA')
        AND COALESCE(por_regional_dev_initiatives, '') ILIKE '%2026 Build Plan%'
        AND COALESCE(TRIM(construction_gc), '') != ''
        AND pj_a_4225_construction_start_finish IS NULL
    """
    regions_q = text(
        f"""
        SELECT DISTINCT region FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {base_where} AND region IS NOT NULL
        ORDER BY region
        """
    )
    markets_q = text(
        f"""
        SELECT DISTINCT m_market FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {base_where} AND m_market IS NOT NULL
        ORDER BY m_market
        """
    )
    sites_q = text(
        f"""
        SELECT DISTINCT s_site_id FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {base_where} AND s_site_id IS NOT NULL
        ORDER BY s_site_id
        """
    )
    vendors_q = text(
        f"""
        SELECT DISTINCT construction_gc FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {base_where} AND construction_gc IS NOT NULL
        ORDER BY construction_gc
        """
    )

    regions = [r[0] for r in db.execute(regions_q)]
    markets = [r[0] for r in db.execute(markets_q)]
    site_ids = [r[0] for r in db.execute(sites_q)]
    vendors = [r[0] for r in db.execute(vendors_q)]

    return {
        "regions": regions,
        "markets": markets,
        "site_ids": site_ids,
        "vendors": vendors,
    }
