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
from typing import Optional, List, Dict
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import STAGING_TABLE
from app.core.filters import apply_geo_filters
from app.models.ahloa import AhloaMilestoneDefinition, AhloaMilestoneColumn, AhloaConstraintThreshold
from app.services.gantt.logic import compute_overall_status
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
    """Fetch all AHLOA milestone definitions from DB, ordered by sort_order.
    AHLOA skip is user-based (not admin is_skipped), applied per-site via user_skips.
    """
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


def is_site_blocked(row: Dict) -> bool:
    """Determine if a site is blocked based on delay comments or codes.
    A site is blocked if either delay comments or delay code is present.
    """
    comments = (row.get("pj_construction_start_delay_comments") or "").strip()
    code = (row.get("pj_construction_complete_delay_code") or "").strip()
    return bool(comments or code)


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


def get_ahloa_milestone_thresholds(db: Session) -> list[dict]:
    """Load milestone-level constraint thresholds for AHLOA from DB."""
    rows = (
        db.query(AhloaConstraintThreshold)
        .filter(
            AhloaConstraintThreshold.constraint_type == "milestone",
            AhloaConstraintThreshold.project_type == "ahloa",
        )
        .order_by(AhloaConstraintThreshold.sort_order)
        .all()
    )
    return [
        {
            "status_label": r.status_label,
            "color": r.color,
            "min_pct": r.min_pct,
            "max_pct": r.max_pct,
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


def _compute_cx_start(row: dict, today: date | None = None) -> tuple[Optional[date], str]:
    """
    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days.

    If the formula result falls in the past, fall back to
    pj_p_4225_construction_start_finish when available.

    Returns (cx_start_date, cx_source) where cx_source is one of:
      "formula", "p_4225_fallback", or "" (when None).
    """
    dates = []
    for col in CX_START_SOURCE_COLUMNS:
        d = parse_date(row.get(col))
        if d:
            dates.append(d)
    if not dates:
        return None, ""

    cx_start = max(dates) + timedelta(days=CX_START_OFFSET_DAYS)

    if today and cx_start < today:
        fallback = parse_date(row.get("pj_p_4225_construction_start_finish"))
        if fallback:
            return fallback, "p_4225_fallback"

    return cx_start, "formula"


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
    cx_date_from: date | None = None,
    cx_date_to: date | None = None,
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
        "pj_construction_start_delay_comments",
        "pj_construction_complete_delay_code",
        "pj_p_4225_construction_start_finish",
    ]

    all_columns = list(fixed_columns)
    seen = set(fixed_columns)
    for col in staging_columns:
        if col not in seen:
            all_columns.append(col)
            seen.add(col)

    columns_sql = ",\n            ".join(all_columns)

    # SQL-level CX date range filter to avoid fetching all 15K+ sites
    cx_filter_sql = ""
    if cx_date_from or cx_date_to:
        cx_expr = (
            f"GREATEST("
            f"COALESCE(pj_p_3710_ran_entitlement_complete_finish::date, '1900-01-01'),"
            f"COALESCE(pj_p_4075_construction_ntp_submitted_to_gc_finish::date, '1900-01-01')"
            f") + INTERVAL '{CX_START_OFFSET_DAYS} days'"
        )
        cx_parts = []
        if cx_date_from:
            cx_parts.append(f"{cx_expr} >= :cx_date_from")
            params["cx_date_from"] = str(cx_date_from)
        if cx_date_to:
            cx_parts.append(f"{cx_expr} <= :cx_date_to")
            params["cx_date_to"] = str(cx_date_to)
        cx_filter_sql = "WHERE " + " AND ".join(cx_parts)

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
    {cx_filter_sql}
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


def _compute_site_milestones(
    row: dict,
    cx_start: Optional[date],
    ahloa_milestones: list[dict],
    column_map: dict,
    nas_data: dict,
    today: date,
    ms_thresholds: list[dict],
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
) -> tuple[list[dict], dict]:
    """
    Compute milestones + status summary for a single AHLOA site.

    Returns (milestones_out, status_summary) where status_summary has keys:
      total, on_track, in_progress, delayed, overall_status, on_track_pct
    """
    milestones_out = []
    on_track_count = 0
    delayed_count = 0
    in_progress_count = 0
    total_ms = 0

    for ms in ahloa_milestones:
        ms_key = ms["key"]

        if skipped_keys and ms_key in skipped_keys:
            continue

        total_ms += 1

        # Apply user SLA override if present
        effective_ms = ms
        if user_expected_days_overrides and ms_key in user_expected_days_overrides:
            effective_ms = {**ms, "expected_days": user_expected_days_overrides[ms_key]}

        actual_date, is_text, text_val, is_status, status_val = _get_milestone_actual(
            row, ms_key, column_map=column_map, nas_data=nas_data,
        )

        status, delay, expected_date_str = _compute_milestone_status(
            milestone=effective_ms,
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
            "expected_days": effective_ms.get("expected_days", 0),
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

    blocked = is_site_blocked(row)
    if blocked:
        overall_status = "Blocked"
        on_track_pct = 0
    else:
        overall_status = compute_overall_status(on_track_count, total_ms, ms_thresholds)
        on_track_pct = round((on_track_count / total_ms * 100), 2) if total_ms > 0 else 0

    status_summary = {
        "total": total_ms,
        "on_track": on_track_count,
        "in_progress": in_progress_count,
        "delayed": delayed_count,
        "overall_status": overall_status,
        "on_track_pct": on_track_pct,
    }

    return milestones_out, status_summary


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
    strict_pace_apply: bool = False,
    status: str | None = None,
    user_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skipped_keys: set[str] | None = None,
    user_skips: list[tuple[str, str | None]] | None = None,
):
    """
    Main AHLOA gantt endpoint — returns site-wise milestone-wise data.

    skipped_keys: global admin-level skips (flat set of milestone keys).
    user_skips: per-user market-wise skips as list of (milestone_key, market|None).
               market=None means skip for all markets.
    """
    from app.services.gantt.service import _apply_pace_constraint, _apply_vendor_capacity

    today = date.today()

    # Load user SLA overrides for AHLOA
    user_ed_overrides = {}
    if user_id:
        from app.models.ahloa import AhloaUserExpectedDays
        ed_rows = config_db.query(AhloaUserExpectedDays).filter(
            AhloaUserExpectedDays.user_id == user_id
        ).all()
        user_ed_overrides = {r.milestone_key: r.expected_days for r in ed_rows if r.expected_days is not None}

    ahloa_milestones = get_ahloa_milestones(db)
    column_map = get_ahloa_column_map(db)
    ms_thresholds = get_ahloa_milestone_thresholds(config_db)

    staging_columns = _get_all_staging_columns(column_map)

    query, params = _build_ahloa_query(
        staging_columns=staging_columns,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit, offset=offset,
        cx_date_from=start_date, cx_date_to=end_date,
    )
    result = db.execute(query, params)
    rows = [dict(r._mapping) for r in result]

    total_count = 0
    count = 0
    if rows:
        total_count = rows[0].get("total_count", 0)
        count = len(rows)

    site_ids = [row["s_site_id"] for row in rows]
    nas_data = _fetch_nas_data(db, site_ids)

    def _effective_skips(site_market: str, site_area: str = "") -> set[str] | None:
        """Merge global admin skips with per-user market/area-wise skips.

        user_skips entries are 3-tuples (milestone_key, market_or_None, area_or_None).
        A row matches a site when:
          - market matches the site's market, OR
          - area matches the site's area, OR
          - both market and area are NULL (skip applies to all markets)
        """
        effective = set(skipped_keys) if skipped_keys else set()
        if user_skips:
            mkt_lower = (site_market or "").strip().lower()
            area_lower = (site_area or "").strip().lower()
            for entry in user_skips:
                # Backward compat: accept either 2-tuple (key, market) or 3-tuple
                if len(entry) == 2:
                    ms_key, mkt = entry
                    ar = None
                else:
                    ms_key, mkt, ar = entry
                mkt_match = mkt is not None and mkt.strip().lower() == mkt_lower
                area_match = ar is not None and ar.strip().lower() == area_lower
                global_match = (mkt is None and ar is None)
                if mkt_match or area_match or global_match:
                    effective.add(ms_key)
        return effective or None

    # =================================================================
    # PHASE 1: Build light site list with CX dates (no milestones yet)
    # =================================================================
    light_sites = []
    row_lookup: dict[str, dict] = {}
    for row in rows:
        cx_start, cx_source = _compute_cx_start(row, today)
        if cx_start < today:
            continue  # skip sites with past CX start after initial computation
        
        if start_date or end_date:
            if cx_start is None:
                continue
            if start_date and cx_start < start_date:
                continue
            if end_date and cx_start > end_date:
                continue

        gc_value = row.get("construction_gc") or ""
        site_key = f"{row['s_site_id']}_{row.get('pj_project_id', '')}"
        row_lookup[site_key] = row

        light_sites.append({
            "site_id": row["s_site_id"],
            "project_id": row.get("pj_project_id") or "",
            "project_name": row.get("pj_project_name") or "",
            "market": row.get("m_market") or "",
            "area": row.get("m_area") or "",
            "region": row.get("region") or "",
            "vendor_name": gc_value,
            "gc_note": "GC not yet assigned." if not gc_value else None,
            "delay_comments": row.get("pj_construction_start_delay_comments") or "",
            "delay_code": row.get("pj_construction_complete_delay_code") or "",
            "forecasted_cx_start_date": str(cx_start) if cx_start else None,
            "forecasted_cx_source": cx_source,
        })

    # 2a. Excel CX overrides
    if user_id:
        from app.services.macro_upload import get_upload_map
        upload_map = get_upload_map(config_db, user_id, project_type="ahloa")
        for site in light_sites:
            uploaded_cx = upload_map.get(f"{site['site_id']}_{site['project_id']}")
            if uploaded_cx:
                site["forecasted_cx_start_date"] = uploaded_cx
                site["forecasted_cx_source"] = "uploaded"

    # 2b. Pace constraints (AHLOA-scoped)
    if (pace_constraint_flag or strict_pace_apply) and user_id:
        light_sites = _apply_pace_constraint(
            light_sites, config_db, pace_constraint_flag, user_id,
            strict_pace_apply=strict_pace_apply, project_type="ahloa",
        )

    # =================================================================
    # PHASE 2: Settle CX dates — vendor capacity + excel + pace
    #          (all BEFORE milestone computation)
    # =================================================================

    # 2c. Vendor capacity (also pulls user windows when user_id provided)
    if consider_vendor_capacity:
        light_sites = _apply_vendor_capacity(
            light_sites, db, config_db=config_db, user_id=user_id, project_type="ahloa",
        )

    # =================================================================
    # PHASE 3: Compute milestones ONCE with settled CX dates
    # =================================================================
    sites = []
    for site in light_sites:
        settled_cx = parse_date(site["forecasted_cx_start_date"])
        site_key = f"{site['site_id']}_{site['project_id']}"
        row = row_lookup.get(site_key)
        if row is None or settled_cx is None:
            # Keep site in output but with no milestones
            site["milestones"] = []
            site["overall_status"] = "CRITICAL"
            site["on_track_pct"] = 0
            site["milestone_status_summary"] = {"total": 0, "on_track": 0, "in_progress": 0, "delayed": 0}
            sites.append(site)
            continue

        site_skips = _effective_skips(site.get("market") or "", site.get("area") or "")
        milestones_out, summary = _compute_site_milestones(
            row, settled_cx, ahloa_milestones, column_map,
            nas_data, today, ms_thresholds, site_skips,
            user_expected_days_overrides=user_ed_overrides,
        )

        site["milestones"] = milestones_out
        site["overall_status"] = summary["overall_status"]
        site["on_track_pct"] = summary["on_track_pct"]
        site["milestone_status_summary"] = {
            "total": summary["total"],
            "on_track": summary["on_track"],
            "in_progress": summary["in_progress"],
            "delayed": summary["delayed"],
        }
        sites.append(site)

    return sites, total_count, count
