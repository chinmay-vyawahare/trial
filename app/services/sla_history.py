"""
SLA History service — compute expected_days from historical actual dates.

For each milestone, looks at completed sites (where actual dates are not null)
within a user-specified date range. Computes the average/median duration between
a milestone's predecessor actual finish and its own actual finish.

For root milestones (no predecessor), expected_days stays 0.
For text-type milestones (e.g. cpo, 4000), duration is not date-based so
they keep their default expected_days.

Skipped milestones (is_skipped=True) are excluded entirely from computation.
When a milestone's predecessor is skipped (or is a text milestone), the service
walks UP the dependency chain to find the nearest non-skipped, date-based
ancestor and uses that instead. This handles chains like:
  A (date) → B (skipped) → C (date)  →  C's history = median(C_actual - A_actual)
  quote (date) → cpo (text) → 1555 (date)  →  1555's history = median(1555_actual - quote_actual)
"""

from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.core.database import STAGING_TABLE
from app.models.prerequisite import MilestoneDefinition
from app.services.gantt.milestones import get_milestones


_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
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


def _get_skipped_keys(config_db: Session) -> set[str]:
    """Return globally skipped milestone keys."""
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


def _find_date_ancestors(
    key: str,
    ms_lookup: dict,
    date_cols_lookup: dict[str, list[str]],
    skipped_keys: set[str],
) -> list[str]:
    """
    Walk up the dependency chain from `key` to find the nearest ancestor(s)
    that have date columns AND are not skipped. Skips over text-only milestones
    and skipped milestones.

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
        if d in skipped_keys:
            # Skipped milestone — walk up further
            result.extend(_find_date_ancestors(d, ms_lookup, date_cols_lookup, skipped_keys))
        elif d in date_cols_lookup:
            # This predecessor has date columns and is not skipped — use it
            result.append(d)
        else:
            # Text milestone (no date columns) — walk up further
            result.extend(_find_date_ancestors(d, ms_lookup, date_cols_lookup, skipped_keys))

    return result


def compute_history_expected_days(
    db: Session,
    config_db: Session,
    date_from: date,
    date_to: date,
    use_median: bool = True,
) -> list[dict]:
    """
    Compute expected_days for each milestone based on historical actual dates.

    For each milestone with a predecessor:
      expected_days = AVG/MEDIAN(milestone_actual - predecessor_actual) in days

    Skipped milestones (is_skipped=True) are excluded and get None for
    history_expected_days. When a predecessor is skipped or is a text milestone,
    walks up to the nearest non-skipped, date-based ancestor.

    Only sites where BOTH actual dates fall within [date_from, date_to]
    are included.

    Returns a list of:
      {milestone_key, milestone_name, default_expected_days,
       history_expected_days, sample_count, is_skipped}
    """
    milestones_config = get_milestones(config_db)
    skipped_keys = _get_skipped_keys(config_db)

    # Build key→milestone lookup and key→date_columns lookup
    ms_lookup = {ms["key"]: ms for ms in milestones_config}
    date_cols_lookup: dict[str, list[str]] = {}
    for ms in milestones_config:
        cols = _get_date_columns(ms)
        if cols:
            date_cols_lookup[ms["key"]] = cols

    results = []

    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]

        result_item = {
            "milestone_key": key,
            "milestone_name": ms["name"],
            "default_expected_days": ms["expected_days"],
            "history_expected_days": None,
            "sample_count": 0,
            "is_skipped": key in skipped_keys,
        }

        # Skipped milestones — exclude from computation
        if key in skipped_keys:
            results.append(result_item)
            continue

        # Root milestone (no predecessor) — stays 0
        if dep is None:
            result_item["history_expected_days"] = 0
            results.append(result_item)
            continue

        # Text-field milestones (e.g. cpo, 4000) have no date column to compute
        # history from — use their existing expected_days from the DB as-is.
        if key not in date_cols_lookup:
            result_item["history_expected_days"] = ms["expected_days"]
            results.append(result_item)
            continue

        # Get the milestone's own date column(s)
        ms_date_cols = date_cols_lookup[key]

        # Get predecessor date column(s), walking past text AND skipped milestones
        ancestor_keys = _find_date_ancestors(key, ms_lookup, date_cols_lookup, skipped_keys)
        pred_date_cols = []
        for ak in ancestor_keys:
            pred_date_cols.extend(date_cols_lookup[ak])

        if not pred_date_cols:
            results.append(result_item)
            continue

        # Build SQL to compute AVG/MEDIAN duration
        cfg_type = (ms.get("column_config") or {}).get("type", "single")
        if cfg_type == "max" and len(ms_date_cols) > 1:
            ms_date_expr = "GREATEST(" + ", ".join(f"{c}::date" for c in ms_date_cols) + ")"
        else:
            ms_date_expr = f"{ms_date_cols[0]}::date"

        if len(pred_date_cols) == 1:
            pred_date_expr = f"{pred_date_cols[0]}::date"
        else:
            pred_date_expr = "GREATEST(" + ", ".join(f"{c}::date" for c in pred_date_cols) + ")"

        # Build null checks for all involved columns
        not_null_checks = []
        for col in ms_date_cols:
            not_null_checks.append(f"{col} IS NOT NULL")
        for col in pred_date_cols:
            not_null_checks.append(f"{col} IS NOT NULL")
        not_null_sql = " AND ".join(not_null_checks)

        if use_median:
            agg_expr = f"ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ({ms_date_expr} - {pred_date_expr})))::int"
        else:
            agg_expr = f"ROUND(AVG(({ms_date_expr} - {pred_date_expr})))::int"

        query = sa_text(f"""
            SELECT
                {agg_expr} AS computed_days,
                COUNT(*) AS sample_count
            FROM {STAGING_TABLE}
            WHERE {_BASE_WHERE}
              AND {not_null_sql}
              AND {ms_date_expr} BETWEEN :date_from AND :date_to
        """)

        row = db.execute(query, {"date_from": date_from, "date_to": date_to}).fetchone()

        if row and row[0] is not None and row[1] > 0:
            avg_days = max(0, row[0])  # clamp to 0 minimum
            result_item["history_expected_days"] = avg_days
            result_item["sample_count"] = row[1]

        results.append(result_item)

    return results
