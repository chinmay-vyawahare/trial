"""
SLA History service — compute expected_days from historical actual dates.

For each milestone, looks at completed sites (where actual dates are not null)
within a user-specified date range. Computes the average/median duration between
a milestone's predecessor actual finish and its own actual finish.

For root milestones (no predecessor), expected_days stays 0.
For text-type milestones (e.g. cpo, 4000), duration is not date-based so
they keep their default expected_days.

When a milestone's predecessor is a text milestone, the service
walks UP the dependency chain to find the nearest date-based
ancestor and uses that instead. This handles chains like:
  quote (date) → cpo (text) → 1555 (date)  →  1555's history = median(1555_actual - quote_actual)
"""

from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.core.database import STAGING_TABLE
from app.services.gantt.milestones import get_milestones


_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NOT NULL"
)


def _get_date_columns(ms: dict) -> list[str] | None:
    """
    Return the date column name(s) for a milestone, or None if it's
    a text-only milestone (no date-based duration).
    """
    cfg = ms.get("column_config") or {}
    cfg_type = cfg.get("type", "single")

    if cfg_type == "text":
        return None  # text milestones have no date duration

    columns = cfg.get("columns", [])
    if cfg_type == "with_status":
        # First column is the date, second is status
        return [columns[0]] if columns else None

    # single or max — all columns are date columns
    return columns if columns else None


def _find_date_ancestors(
    key: str,
    ms_lookup: dict,
    date_cols_lookup: dict[str, list[str]],
) -> list[str]:
    """
    Walk up the dependency chain from `key` to find the nearest ancestor(s)
    that have date columns. Skips over text-only milestones.

    Returns a list of milestone keys with date columns.
    """
    ms = ms_lookup.get(key)
    if not ms:
        return []

    dep = ms["depends_on"]
    if dep is None:
        return []

    dep_list = dep if isinstance(dep, list) else [dep]
    result = []

    for d in dep_list:
        if d in date_cols_lookup:
            # This predecessor has date columns — use it
            result.append(d)
        else:
            # Text milestone (no date columns) — walk up further
            result.extend(_find_date_ancestors(d, ms_lookup, date_cols_lookup))

    return result


def _build_filter_clauses(
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
) -> tuple[str, dict]:
    """Build WHERE clause fragments and params for geographic/gate filters."""
    from app.core.filters import apply_geo_filters

    clauses: list[str] = []
    params: dict = {}

    apply_geo_filters(
        clauses, params,
        region=region, market=market, area=area,
        site_id=site_id, vendor=vendor,
        prefix="f_",
    )

    if plan_type_include:
        placeholders = ", ".join(f":f_pti_{i}" for i in range(len(plan_type_include)))
        clauses.append(f"por_plan_type IN ({placeholders})")
        for i, val in enumerate(plan_type_include):
            params[f"f_pti_{i}"] = val
    if regional_dev_initiatives:
        clauses.append("COALESCE(por_regional_dev_initiatives, '') ILIKE :f_rdi_pattern")
        params["f_rdi_pattern"] = f"%{regional_dev_initiatives}%"

    sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def compute_history_expected_days(
    db: Session,
    config_db: Session,
    date_from: date,
    date_to: date,
    use_median: bool = True,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    view_type: str = "forecast",
) -> list[dict]:
    """
    Compute history-based duration for each milestone from actual dates.

    view_type="forecast" (left-to-right):
      history_expected_days = MEDIAN(milestone_actual - predecessor_actual)
      Walks past text predecessors to the nearest date-based ancestor.

    view_type="actual" (right-to-left):
      history_expected_days = MEDIAN(pj_a_4225_construction_start_finish - milestone_actual)
      i.e. the historical back_days from cx anchor to each milestone.

    Only sites where the relevant dates fall within [date_from, date_to]
    are included. Geographic and gate-check filters are applied when provided.

    Returns a list of:
      {milestone_key, milestone_name, default_expected_days,
       history_expected_days, sample_count}
    """
    filter_sql, filter_params = _build_filter_clauses(
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
    )

    milestones_config = get_milestones(config_db)

    # Build key→milestone lookup and key→date_columns lookup
    ms_lookup = {ms["key"]: ms for ms in milestones_config}
    date_cols_lookup: dict[str, list[str]] = {}
    for ms in milestones_config:
        cols = _get_date_columns(ms)
        if cols:
            date_cols_lookup[ms["key"]] = cols

    is_actual = view_type == "actual"
    cx_col = "pj_a_4225_construction_start_finish"

    # In actual (right-to-left) mode, we anchor against pj_a_4225 which must
    # exist (construction has started). The default _BASE_WHERE forces it to
    # be NULL — flip that for actual mode.
    if is_actual:
        base_where_sql = (
            "smp_name = 'NTM' "
            "AND COALESCE(TRIM(construction_gc), '') != '' "
            f"AND {cx_col} IS NOT NULL"
        )
    else:
        base_where_sql = _BASE_WHERE

    results = []

    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]

        # Per-milestone fallback when history can't be computed.
        # Forecast → MilestoneDefinition.expected_days
        # Actual   → MilestoneDefinition.back_days (may be None if not seeded)
        ms_def_fallback = ms.get("back_days") if is_actual else ms["expected_days"]

        result_item = {
            "milestone_key": key,
            "milestone_name": ms["name"],
            "default_expected_days": ms["expected_days"],
            "history_expected_days": ms_def_fallback,
            "sample_count": 0,
        }

        if not is_actual:
            # ---------- forecast (left-to-right) ----------
            # Root milestone (no predecessor) — stays 0
            if dep is None:
                result_item["history_expected_days"] = 0
                results.append(result_item)
                continue

            # Text-field milestones — no date column; use default expected_days
            if key not in date_cols_lookup:
                result_item["history_expected_days"] = ms["expected_days"]
                results.append(result_item)
                continue

            ms_date_cols = date_cols_lookup[key]

            # Walk past text predecessors to nearest date-based ancestor(s)
            ancestor_keys = _find_date_ancestors(key, ms_lookup, date_cols_lookup)
            pred_date_cols = []
            for ak in ancestor_keys:
                pred_date_cols.extend(date_cols_lookup[ak])

            if not pred_date_cols:
                results.append(result_item)
                continue

            cfg_type = (ms.get("column_config") or {}).get("type", "single")
            if cfg_type == "max" and len(ms_date_cols) > 1:
                ms_date_expr = "GREATEST(" + ", ".join(f"{c}::date" for c in ms_date_cols) + ")"
            else:
                ms_date_expr = f"{ms_date_cols[0]}::date"

            if len(pred_date_cols) == 1:
                pred_date_expr = f"{pred_date_cols[0]}::date"
            else:
                pred_date_expr = "GREATEST(" + ", ".join(f"{c}::date" for c in pred_date_cols) + ")"

            not_null_checks = [f"{c} IS NOT NULL" for c in ms_date_cols]
            not_null_checks += [f"{c} IS NOT NULL" for c in pred_date_cols]
            not_null_sql = " AND ".join(not_null_checks)

            duration_expr = f"({ms_date_expr} - {pred_date_expr})"
            window_sql = f"AND {ms_date_expr} BETWEEN :date_from AND :date_to"

        else:
            # ---------- actual (right-to-left) ----------
            # Text-only milestones have no date anchor — leave as None
            if key not in date_cols_lookup:
                results.append(result_item)
                continue

            ms_date_cols = date_cols_lookup[key]

            cfg_type = (ms.get("column_config") or {}).get("type", "single")
            if cfg_type == "max" and len(ms_date_cols) > 1:
                ms_date_expr = "GREATEST(" + ", ".join(f"{c}::date" for c in ms_date_cols) + ")"
            else:
                ms_date_expr = f"{ms_date_cols[0]}::date"

            not_null_sql = " AND ".join([f"{c} IS NOT NULL" for c in ms_date_cols])

            duration_expr = f"({cx_col}::date - {ms_date_expr})"
            # Only bind the cx anchor to the date window. Milestone actuals
            # naturally precede cx and would be filtered out if also bounded.
            window_sql = f"AND {cx_col}::date BETWEEN :date_from AND :date_to"

        if use_median:
            agg_expr = f"ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {duration_expr}))::int"
        else:
            agg_expr = f"ROUND(AVG({duration_expr}))::int"

        query = sa_text(f"""
            SELECT
                {agg_expr} AS computed_days,
                COUNT(*) AS sample_count
            FROM {STAGING_TABLE}
            WHERE {base_where_sql}
              AND {not_null_sql}
              {window_sql}
              {filter_sql}
        """)

        row = db.execute(query, {"date_from": date_from, "date_to": date_to, **filter_params}).fetchone()

        if row and row[0] is not None and row[1] > 0:
            avg_days = max(0, row[0])  # clamp to 0 minimum
            result_item["history_expected_days"] = avg_days
            result_item["sample_count"] = row[1]

        results.append(result_item)

    return results
