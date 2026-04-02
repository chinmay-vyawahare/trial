"""
AHLOA Gantt Chart Service

CX Start Date per site = Max(pj_p_3710_ran_entitlement_complete_finish,
                             pj_p_4075_construction_ntp_submitted_to_gc_finish) + 50 days

Each milestone's expected date = CX Start + (offset_weeks * 7 days)
Status: compare actual date/value against expected date.

Milestone definitions and column mappings are loaded from
ahloa_milestone_seed_data.py (will move to DB later).
"""

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import STAGING_TABLE
from app.core.filters import apply_geo_filters
from app.services.gantt.utils import parse_date

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# CX Start config
# ----------------------------------------------------------------
CX_START_OFFSET_DAYS = 50
CX_START_SOURCE_COLUMNS = [
    "pj_p_3710_ran_entitlement_complete_finish",
    "pj_p_4075_construction_ntp_submitted_to_gc_finish",
]

# ----------------------------------------------------------------
# Milestone definitions — matches existing DB schema (no extra cols)
#
# These go into milestone_definitions / milestone_columns tables as-is.
# Fields: key, name, sort_order, expected_days, depends_on,
#         start_gap_days, task_owner, phase_type
# ----------------------------------------------------------------
AHLOA_MILESTONES = [
    {"key": "cpo",              "name": "CPO For Site",                              "sort_order": 1,  "expected_days": 0,  "depends_on": None,             "start_gap_days": 0, "task_owner": "TMO",    "phase_type": "Pre-CX Phase"},
    {"key": "3850",             "name": "BOM Ready (MS 3850)",                       "sort_order": 2,  "expected_days": 42, "depends_on": None,             "start_gap_days": 0, "task_owner": "CM",    "phase_type": "Material Phase"},
    {"key": "3875",             "name": "BOM Material Available in MSL (MS 3875)",   "sort_order": 3,  "expected_days": 10,  "depends_on": None,           "start_gap_days": 0, "task_owner": "TMO",    "phase_type": "Material Phase"},
    {"key": "3925",             "name": "Material Pickup by GC (MS 3925)",           "sort_order": 4,  "expected_days": 7,  "depends_on": None,           "start_gap_days": 0, "task_owner": "GC",     "phase_type": "Material Phase"},
    {"key": "4000",             "name": "LL NTP Ready (MS 4000)",                    "sort_order": 5,  "expected_days": 28, "depends_on": None,             "start_gap_days": 0, "task_owner": "TMO",    "phase_type": "NTP Phase"},
    {"key": "4075",             "name": "Overall NTP Ready (MS 4075)",               "sort_order": 6,  "expected_days": 28, "depends_on": None,             "start_gap_days": 0, "task_owner": "TMO",    "phase_type": "NTP Phase"},
    {"key": "4100",             "name": "Final NTP Ready (MS 4100)",                 "sort_order": 7, "expected_days": 28, "depends_on": None,           "start_gap_days": 0, "task_owner": "PDM",     "phase_type": "NTP Phase"},
    {"key": "spo_gc_cx",        "name": "SPO to GC for CX",                          "sort_order": 8, "expected_days": 42, "depends_on": None,             "start_gap_days": 0, "task_owner": "PROJECT-OPS",    "phase_type": "SPO Phase"},
    {"key": "crane",            "name": "Crane",                                     "sort_order": 9, "expected_days": 14, "depends_on": None,             "start_gap_days": 0, "task_owner": "GC",     "phase_type": "Crane Readiness Phase"},
    {"key": "talon_scoping",    "name": "Talon Session for Scoping",                 "sort_order": 10, "expected_days": 14, "depends_on": None,             "start_gap_days": 0, "task_owner": "SE-CoE", "phase_type": "Scoping Phase"},
    {"key": "talon_scop",       "name": "Talon Session for SCOP",                    "sort_order": 11, "expected_days": 14, "depends_on": None,             "start_gap_days": 0, "task_owner": "SE-CoE", "phase_type": "SCOP Phase"},
    {"key": "nas_upload",       "name": "Planned Activity Upload Status in NAS",     "sort_order": 12, "expected_days": 7,  "depends_on": None,             "start_gap_days": 0, "task_owner": "GC",     "phase_type": "Outage Readiness Phase"},
]

# ----------------------------------------------------------------
# Column mapping — matches existing milestone_columns table schema
#
# Fields: milestone_key, column_name, column_role, logic
# ----------------------------------------------------------------
AHLOA_COLUMN_MAP = {
    "cpo":              {"column_name": "ms_1555_construction_complete_cpo_custom_field", "column_role": "text", "logic": None},
    "3850":             {"column_name": "pj_a_3850_bom_submitted_bom_in_bat_finish", "column_role": "date", "logic": None},
    "3875":             {"column_name": "pj_a_3875_bom_received_bom_in_aims_finish", "column_role": "date", "logic": None},
    "3925":             {"column_name": "pj_a_3925_msl_pickup_date_finish", "column_role": "date", "logic": None},
    "4000":             {"column_name": "pj_a_4000_ll_ntp_received", "column_role": "text", "logic": None},
    "4075":             {"column_name": "pj_a_4075_construction_ntp_submitted_to_gc_finish", "column_role": "date", "logic": None},
    "4100":             {"column_name": "pj_a_4100_construction_ntp_accepted_by_gc_finish", "column_role": "date", "logic": None},
    "spo_gc_cx":        {"column_name": "ms1555_construction_complete_spo_issued_date", "column_role": "date", "logic": None},
    "crane":            {"column_name": "scoping_package_crane_required", "column_role": "status", "logic": {"on_track": ["Yes","No"], "delayed": ["null", "", None]}},
    "talon_scoping":    {"column_name": "scoping_package_create_date", "column_role": "date", "logic": None},
    "talon_scop":       {"column_name": "ms_1557_punch_checklist_reviewed_and_submitted_to_tmobile_atl", "column_role": "date", "logic": None},
    "nas_upload":       {"column_name": "nas_activity_end_date", "column_role": "date", "logic": {"source_table": "nas_planned_outage_activity", "join_column": "nas_site_id", "filter": {"nas_project_category": "AHLOB"}}},
}



def _get_all_staging_columns() -> list[str]:
    """Collect all staging table columns needed for AHLOA milestones."""
    cols = set()
    # CX start source columns
    for c in CX_START_SOURCE_COLUMNS:
        cols.add(c)
    # Milestone columns (skip NAS — separate table)
    for key, col_entry in AHLOA_COLUMN_MAP.items():
        logic = col_entry.get("logic")
        if logic and isinstance(logic, dict) and "source_table" in logic:
            continue  # skip external table columns
        cols.add(col_entry["column_name"])
    return sorted(cols)


def _compute_cx_start(row: dict) -> Optional[date]:
    """
    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days.
    Returns None if neither source column has a valid date.
    """
    dates = []
    for col in CX_START_SOURCE_COLUMNS:
        d = parse_date(row.get(col))
        if d:
            dates.append(d)
    if not dates:
        return None
    return max(dates) + timedelta(days=CX_START_OFFSET_DAYS)


def _get_milestone_actual(row: dict, milestone_key: str, nas_data: dict | None = None):
    """
    Extract actual value for a milestone from the row.

    Returns (actual_date, is_text, text_val, is_status, status_val)
    """
    col_entry = AHLOA_COLUMN_MAP.get(milestone_key)
    if not col_entry:
        return None, False, None, False, None

    col_name = col_entry["column_name"]
    col_role = col_entry["column_role"]
    logic = col_entry.get("logic")

    # Handle external table (NAS)
    if logic and isinstance(logic, dict) and "source_table" in logic:
        site_id = row.get("s_site_id")
        if nas_data and site_id:
            nas_val = nas_data.get(site_id)
            if nas_val:
                return parse_date(nas_val), False, None, False, None
        return None, False, None, False, None

    raw_val = row.get(col_name)

    if col_role == "text":
        text_val = (str(raw_val) if raw_val else "").strip()
        return None, True, text_val, False, None

    if col_role == "status":
        status_val = (str(raw_val) if raw_val else "").strip()
        return None, False, None, True, status_val

    # date role
    return parse_date(raw_val), False, None, False, None


def _compute_milestone_status(
    milestone: dict,
    actual_date: Optional[date],
    is_text: bool,
    text_val: Optional[str],
    is_status: bool,
    status_val: Optional[str],
    cx_start: Optional[date],
    today: date,
) -> tuple[str, int, Optional[str]]:
    """
    Compute status for a single AHLOA milestone.

    Returns (status, delay_days, expected_date_str)
    """
    key = milestone["key"]
    expected_days = milestone.get("expected_days", 0)

    # --- Status check milestones (crane) ---
    if is_status:
        col_entry = AHLOA_COLUMN_MAP.get(key)
        logic = col_entry.get("logic") if col_entry else None

        on_track_values = (logic or {}).get("on_track", [])
        if status_val and status_val in on_track_values:
            return "On Track", 0, None
        return "Delayed", 0, None

    # --- Text presence milestones (cpo, survey_eligible, 4000) ---
    if is_text:
        if text_val and text_val.strip():
            return "On Track", 0, None
        return "Delayed", 0, None

    # --- Date milestones with expected_days offset from CX start ---
    if expected_days > 0 and cx_start:
        
        expected = cx_start - timedelta(days=expected_days)

        expected_str = str(expected)

        if actual_date:
            delay = (actual_date - expected).days
            if delay <= 0:
                return "On Track", 0, expected_str
            return "Delayed", delay, expected_str

        # No actual date yet
        remaining = (expected - today).days
        if remaining >= 0:
            return "In Progress", 0, expected_str
        return "Delayed", abs(remaining), expected_str

    # --- Date presence milestones (survey_spo, etc. — no offset) ---
    if actual_date:
        return "On Track", 0, None
    return "Delayed", 0, None


def _build_ahloa_query(
    staging_columns: list[str],
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    limit: int = None,
    offset: int = None,
):
    """Build the SQL query for AHLOA sites from the staging table."""
    where_clauses = [
        "pj_hard_cost_vendor_assignment_po ILIKE '%NOKIA%'",
        "por_release_version = 'Radio Upgrade NR'",
        "por_plan_added_date > '2025-03-28'",
        "pj_a_4225_construction_start_finish IS NULL",
    ]
    params = {}

    apply_geo_filters(
        where_clauses, params,
        region=region, market=market, area=area,
        site_id=site_id, vendor=vendor,
    )

    where_sql = " AND ".join(where_clauses)

    pagination_sql = ""
    if limit is not None:
        pagination_sql += f" LIMIT {int(limit)}"
    if offset is not None:
        pagination_sql += f" OFFSET {int(offset)}"

    fixed_columns = [
        "s_site_id",
        "pj_project_id",
        "pj_project_name",
        "m_market",
        "m_area",
        "region",
        "construction_gc",
    ]

    all_columns = list(fixed_columns)
    seen = set(fixed_columns)
    for col in staging_columns:
        if col not in seen:
            all_columns.append(col)
            seen.add(col)

    columns_sql = ",\n            ".join(all_columns)

    query = text(f"""
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
    """)

    return query, params


def _fetch_nas_data(db: Session, site_ids: list[str]) -> dict[str, str]:
    """
    Fetch NAS activity end dates for AHLOB project category.

    Returns {site_id: nas_activity_end_date} mapping.
    """
    if not site_ids:
        return {}

    query = text("""
        SELECT nas_site_id, nas_activity_end_date
        FROM pwc_macro_staging_schema.nas_planned_outage_activity
        WHERE nas_project_category = 'AHLOB'
          AND nas_site_id = ANY(:site_ids)
          AND nas_activity_end_date IS NOT NULL
    """)
    
    params = {"site_ids": site_ids}

    try:
        rows = db.execute(query, params).fetchall()
        return {str(r[0]): r[1] for r in rows}
    except Exception as e:
        logger.warning("Failed to fetch NAS data: %s", e)
        return {}


def get_ahloa_gantt(
    db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    limit: int = None,
    offset: int = None,
):
    """
    Main AHLOA gantt endpoint — returns site-wise milestone-wise data.

    For each site:
      1. Calculate CX Start = Max(3710, 4075) + 50 days
      2. For each milestone, compute expected date = CX Start + offset_weeks
      3. Compare actual vs expected → On Track / In Progress / Delayed
    """
    today = date.today()

    staging_columns = _get_all_staging_columns()

    query, params = _build_ahloa_query(
        staging_columns=staging_columns,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        limit=limit, offset=offset,
    )
    result = db.execute(query, params)
    rows = [dict(r._mapping) for r in result]

    total_count = 0
    count = 0
    if rows:
        total_count = rows[0].get("total_count", 0)
        count = len(rows)

    # Fetch NAS data for all sites in one query
    site_ids = [row["s_site_id"] for row in rows]
    nas_data = _fetch_nas_data(db, site_ids)

    sites = []
    for row in rows:
        cx_start = _compute_cx_start(row)

        milestones_out = []
        on_track_count = 0
        delayed_count = 0
        in_progress_count = 0
        total_ms = 0

        for ms in AHLOA_MILESTONES:
            ms_key = ms["key"]
            total_ms += 1

            actual_date, is_text, text_val, is_status, status_val = _get_milestone_actual(
                row, ms_key, nas_data=nas_data,
            )

            status, delay, expected_date_str = _compute_milestone_status(
                milestone=ms,
                actual_date=actual_date,
                is_text=is_text,
                text_val=text_val,
                is_status=is_status,
                status_val=status_val,
                cx_start=cx_start,
                today=today,
            )

            if status == "On Track":
                on_track_count += 1
            elif status == "Delayed":
                delayed_count += 1
            else:
                in_progress_count += 1

            milestones_out.append({
                "key": ms_key,
                "name": ms["name"],
                "sort_order": ms["sort_order"],
                "expected_days": ms.get("expected_days", 0),
                "task_owner": ms.get("task_owner"),
                "phase_type": ms.get("phase_type"),
                "expected_date": expected_date_str,
                "actual_finish": (
                    str(actual_date) if actual_date
                    else (text_val if is_text and text_val else
                          (status_val if is_status else None))
                ),
                "status": status,
                "delay_days": delay,
            })

        # Compute overall status
        if total_ms > 0:
            on_track_pct = round((on_track_count / total_ms) * 100, 2)
        else:
            on_track_pct = 0

        if on_track_pct >= 60:
            overall_status = "ON TRACK"
        elif on_track_pct >= 30:
            overall_status = "IN PROGRESS"
        else:
            overall_status = "CRITICAL"

        sites.append({
            "site_id": row["s_site_id"],
            "project_id": row.get("pj_project_id") or "",
            "project_name": row.get("pj_project_name") or "",
            "market": row.get("m_market") or "",
            "area": row.get("m_area") or "",
            "region": row.get("region") or "",
            "vendor_name": row.get("construction_gc") or "",
            "forecasted_cx_start_date": str(cx_start) if cx_start else None,
            "milestones": milestones_out,
            "overall_status": overall_status,
            "on_track_pct": on_track_pct,
            "milestone_status_summary": {
                "total": total_ms,
                "on_track": on_track_count,
                "in_progress": in_progress_count,
                "delayed": delayed_count,
            },
        })

    return sites, total_count, count
