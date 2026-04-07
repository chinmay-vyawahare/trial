"""
AHLOA Gantt Chart Service

CX Start Date per site = Max(pj_p_3710_ran_entitlement_complete_finish,
                             pj_p_4075_construction_ntp_submitted_to_gc_finish) + 50 days

Each milestone's expected date = CX Start + (offset_weeks * 7 days)
Status: compare actual date/value against expected date.

Milestone definitions and column mappings are loaded from DB
(ahloa_milestone_definitions / ahloa_milestone_columns tables).
"""

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import STAGING_TABLE
from app.core.filters import apply_geo_filters
from app.models.ahloa import AhloaMilestoneDefinition, AhloaMilestoneColumn
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
# DB loaders
# ----------------------------------------------------------------
def _parse_logic(raw):
    """Parse the logic JSON column, return dict or None."""
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, ValueError):
        return None


def get_ahloa_milestones(db: Session) -> list[dict]:
    """Fetch all AHLOA milestone definitions from DB, ordered by sort_order."""
    rows = (
        db.query(AhloaMilestoneDefinition)
        .order_by(AhloaMilestoneDefinition.sort_order)
        .all()
    )
    return [
        {
            "key": r.key,
            "name": r.name,
            "sort_order": r.sort_order,
            "expected_days": r.expected_days,
            "depends_on": r.depends_on,
            "start_gap_days": r.start_gap_days,
            "task_owner": r.task_owner,
            "phase_type": r.phase_type,
        }
        for r in rows
    ]


def get_ahloa_column_map(db: Session) -> dict[str, dict]:
    """
    Fetch all AHLOA milestone columns from DB, keyed by milestone_key.

    Returns {milestone_key: {"column_name": ..., "column_role": ..., "logic": ...}}
    """
    rows = (
        db.query(AhloaMilestoneColumn)
        .order_by(AhloaMilestoneColumn.sort_order)
        .all()
    )
    col_map = {}
    for r in rows:
        col_map[r.milestone_key] = {
            "column_name": r.column_name,
            "column_role": r.column_role,
            "logic": _parse_logic(r.logic),
        }
    return col_map


def get_ahloa_milestone_by_key(db: Session, key: str) -> dict | None:
    """Fetch a single AHLOA milestone definition by key."""
    r = db.query(AhloaMilestoneDefinition).filter_by(key=key).first()
    if not r:
        return None
    return {
        "key": r.key,
        "name": r.name,
        "sort_order": r.sort_order,
        "expected_days": r.expected_days,
        "depends_on": r.depends_on,
        "start_gap_days": r.start_gap_days,
        "task_owner": r.task_owner,
        "phase_type": r.phase_type,
    }


def get_ahloa_columns_for_milestone(db: Session, milestone_key: str) -> list[dict]:
    """Fetch all AHLOA columns for a given milestone key."""
    rows = (
        db.query(AhloaMilestoneColumn)
        .filter_by(milestone_key=milestone_key)
        .order_by(AhloaMilestoneColumn.sort_order)
        .all()
    )
    return [
        {
            "milestone_key": r.milestone_key,
            "column_name": r.column_name,
            "column_role": r.column_role,
            "logic": _parse_logic(r.logic),
            "sort_order": r.sort_order,
        }
        for r in rows
    ]


def _get_all_staging_columns(column_map: dict) -> list[str]:
    """Collect all staging table columns needed for AHLOA milestones."""
    cols = set()
    # CX start source columns
    for c in CX_START_SOURCE_COLUMNS:
        cols.add(c)
    # Milestone columns (skip NAS — separate table)
    for key, col_entry in column_map.items():
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


def _get_milestone_actual(row: dict, milestone_key: str, column_map: dict, nas_data: dict | None = None):
    """
    Extract actual value for a milestone from the row.

    Returns (actual_date, is_text, text_val, is_status, status_val)
    """
    col_entry = column_map.get(milestone_key)
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
    column_map: dict,
) -> tuple[str, int, Optional[str]]:
    """
    Compute status for a single AHLOA milestone.

    Returns (status, delay_days, expected_date_str)
    """
    key = milestone["key"]
    expected_days = milestone.get("expected_days", 0)

    # --- Status check milestones (crane) ---
    if is_status:
        col_entry = column_map.get(key)
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
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
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
        FROM pwc_macro_staging_schema.stg_nas_planned_outage_activity
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
    config_db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    status: str | None = None,
    user_id: str | None = None,
):
    """
    Main AHLOA gantt endpoint — returns site-wise milestone-wise data.

    For each site:
      1. Calculate CX Start = Max(3710, 4075) + 50 days
      2. For each milestone, compute expected date = CX Start + offset_weeks
      3. Compare actual vs expected → On Track / In Progress / Delayed
    """
    today = date.today()

    # Load milestone definitions and column mappings from DB
    ahloa_milestones = get_ahloa_milestones(db)
    column_map = get_ahloa_column_map(db)

    staging_columns = _get_all_staging_columns(column_map)

    query, params = _build_ahloa_query(
        staging_columns=staging_columns,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
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

        for ms in ahloa_milestones:
            ms_key = ms["key"]
            total_ms += 1

            actual_date, is_text, text_val, is_status, status_val = _get_milestone_actual(
                row, ms_key, column_map=column_map, nas_data=nas_data,
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
                column_map=column_map,
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
