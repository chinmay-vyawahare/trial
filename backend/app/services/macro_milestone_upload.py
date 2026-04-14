"""
Macro Milestone Actual Upload Service.

Parses CSV/Excel files containing per-milestone actual dates per site+project,
validates columns against the current MilestoneDefinition + MilestoneColumn
schema (which can change as admins add/remove prerequisites), and persists
the payload per user. On each upload for a user, the previous payload is
fully replaced — only the latest upload is retained per user.
"""

import io
import json
import logging
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.prerequisite import (
    MilestoneDefinition,
    MilestoneColumn,
    MacroMilestoneUploadedData,
)

logger = logging.getLogger(__name__)


FIXED_COLUMNS = ("SITE_ID", "REGION", "MARKET", "PROJECT_ID")
REQUIRED_COLUMNS = ("SITE_ID", "PROJECT_ID")
STATUS_SUFFIX = " - Status"
_VALID_STATUS_CANONICAL = {"A", "N", "Not Applicable", ""}
# Case-insensitive lookup of valid statuses → canonical form
VALID_STATUS_LOOKUP = {v.lower(): v for v in _VALID_STATUS_CANONICAL}


# ----------------------------------------------------------------
# File parsing
# ----------------------------------------------------------------

def parse_upload_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or Excel bytes into a DataFrame and normalise headers."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file type: {filename}. Use .csv, .xlsx, or .xls")

    df.columns = [str(c).strip() for c in df.columns]
    return df


# ----------------------------------------------------------------
# Dynamic schema from MilestoneDefinition
# ----------------------------------------------------------------

def _load_milestone_schema(db: Session) -> dict[str, dict]:
    """
    Build a name-keyed map of the active milestone schema:
        {
          milestone_name (case-insensitive): {
              "key": str,
              "name": str,
              "type": "single" | "max" | "text" | "with_status",
              "date_cols": [str, ...],    # staging column(s) for the date
              "status_col": str | None,   # staging column for the status (with_status only)
              "skip_values": list[str],   # status values treated as "skip" (with_status only)
              "use_date_values": list[str],
          }
        }
    """
    ms_rows = db.query(MilestoneDefinition).filter(MilestoneDefinition.is_skipped == False).all()
    col_rows = db.query(MilestoneColumn).all()

    cols_by_ms: dict[str, list] = {}
    for c in col_rows:
        cols_by_ms.setdefault(c.milestone_key, []).append(c)

    schema: dict[str, dict] = {}
    for ms in ms_rows:
        cols = sorted(cols_by_ms.get(ms.key, []), key=lambda c: c.sort_order or 0)
        roles = {c.column_role for c in cols}
        date_cols = [c.column_name for c in cols if c.column_role == "date"]
        text_cols = [c.column_name for c in cols if c.column_role == "text"]
        status_cols = [c for c in cols if c.column_role == "status"]

        entry: dict[str, Any] = {
            "key": ms.key,
            "name": ms.name,
            "type": "single",
            "date_cols": date_cols or text_cols,
            "status_col": None,
            "skip_values": [],
            "use_date_values": [],
        }

        if "text" in roles and not date_cols and not status_cols:
            entry["type"] = "text"
        elif status_cols and date_cols:
            entry["type"] = "with_status"
            entry["status_col"] = status_cols[0].column_name
            status_logic = _parse_json(status_cols[0].logic) or {}
            entry["skip_values"] = status_logic.get("skip", [])
            entry["use_date_values"] = status_logic.get("use_date", [])
        elif len(date_cols) > 1:
            entry["type"] = "max"

        schema[ms.name.strip().lower()] = entry

    return schema


def _parse_json(raw):
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


# ----------------------------------------------------------------
# Value parsing
# ----------------------------------------------------------------

_DATE_FORMATS = (
    "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y",
    "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%y",
)


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean_text(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    return s


# ----------------------------------------------------------------
# Header validation
# ----------------------------------------------------------------

def validate_headers(df_columns: list[str], schema: dict[str, dict]) -> list[str]:
    """
    Validate the CSV headers. Returns a list of error messages (empty = OK).

    Every column beyond the fixed four must either:
      - match a MilestoneDefinition.name (case-insensitive, trimmed), OR
      - match "{name} - Status" for a with_status milestone.
    """
    errors: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df_columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")

    unknown = []
    for col in df_columns:
        if col in FIXED_COLUMNS:
            continue
        norm = col.strip().lower()
        if norm.endswith(STATUS_SUFFIX.lower()):
            base = norm[: -len(STATUS_SUFFIX)].strip()
            if base not in schema:
                unknown.append(col)
                continue
            if schema[base]["type"] != "with_status":
                errors.append(
                    f"Column '{col}' is marked as Status but milestone "
                    f"'{schema[base]['name']}' is not a with_status milestone"
                )
            continue
        if norm not in schema:
            unknown.append(col)

    if unknown:
        errors.append(
            "Unknown columns (no matching milestone name): "
            + ", ".join(f"'{u}'" for u in unknown)
        )
    return errors


# ----------------------------------------------------------------
# Row → milestone payload
# ----------------------------------------------------------------

def _build_milestone_payload(
    row: pd.Series,
    df_columns: list[str],
    schema: dict[str, dict],
) -> tuple[dict, list[str]]:
    """
    Turn one CSV row into the `milestone_actuals` JSON payload keyed by
    milestone key. Returns (payload, row_errors). Blank cells are skipped.
    """
    payload: dict[str, Any] = {}
    errors: list[str] = []

    # First pass: collect status columns so we can attach them to their
    # with_status milestone entries
    status_by_key: dict[str, str] = {}
    for col in df_columns:
        if col in FIXED_COLUMNS:
            continue
        norm = col.strip().lower()
        if norm.endswith(STATUS_SUFFIX.lower()):
            base = norm[: -len(STATUS_SUFFIX)].strip()
            ms = schema.get(base)
            if not ms:
                continue
            raw = _clean_text(row.get(col))
            if raw is None:
                continue
            canonical = VALID_STATUS_LOOKUP.get(raw.strip().lower())
            if canonical is None:
                errors.append(
                    f"Invalid status '{raw}' for '{ms['name']}' — "
                    f"must be one of: A, N, Not Applicable, or blank (case-insensitive)"
                )
                continue
            status_by_key[ms["key"]] = canonical

    # Second pass: date/text values
    for col in df_columns:
        if col in FIXED_COLUMNS:
            continue
        norm = col.strip().lower()
        if norm.endswith(STATUS_SUFFIX.lower()):
            continue

        ms = schema.get(norm)
        if not ms:
            continue  # already caught in validate_headers
        raw = _clean_text(row.get(col))

        mtype = ms["type"]

        if mtype == "text":
            if raw is not None:
                payload[ms["key"]] = raw
            continue

        if mtype in ("single", "max"):
            if raw is None:
                continue
            d = _parse_date(raw)
            if d is None:
                errors.append(
                    f"Invalid date '{raw}' for '{ms['name']}' — "
                    f"accepted formats: M/D/YYYY, YYYY-MM-DD"
                )
                continue
            payload[ms["key"]] = d.isoformat()
            continue

        if mtype == "with_status":
            status_val = status_by_key.pop(ms["key"], None)
            d = _parse_date(raw) if raw is not None else None
            if raw is not None and d is None:
                errors.append(
                    f"Invalid date '{raw}' for '{ms['name']}'"
                )
                continue
            # Save an entry when either side is present
            if d is not None or status_val is not None:
                payload[ms["key"]] = {
                    "date": d.isoformat() if d else None,
                    "status": status_val,
                }
            continue

    # Any leftover status-only entries (milestone date column wasn't present
    # in the CSV but status was provided)
    for key, status_val in status_by_key.items():
        payload[key] = {"date": None, "status": status_val}

    return payload, errors


# ----------------------------------------------------------------
# Public: upsert-as-replace per user
# ----------------------------------------------------------------

def replace_uploaded_data(
    db: Session,
    df: pd.DataFrame,
    uploaded_by: str,
) -> dict:
    """
    Fully replace this user's milestone-upload data with the contents of `df`.

    Steps:
      1. Validate headers against the live MilestoneDefinition schema.
      2. Parse every row — date/text/with_status values go into
         `milestone_actuals` JSON.
      3. DELETE all existing rows for this user.
      4. INSERT one row per CSV row.
      5. Commit.

    Returns: {inserted, skipped, errors: {row_num: [...]}, warnings: [...] }
    """
    schema = _load_milestone_schema(db)

    df_columns = list(df.columns)
    header_errors = validate_headers(df_columns, schema)
    if header_errors:
        return {
            "ok": False,
            "header_errors": header_errors,
            "inserted": 0,
            "skipped": 0,
        }

    parsed_rows: list[dict] = []
    row_errors: dict[int, list[str]] = {}
    seen_keys: set[tuple[str, str]] = set()
    skipped = 0

    for idx, row in df.iterrows():
        site_id = _clean_text(row.get("SITE_ID"))
        project_id = _clean_text(row.get("PROJECT_ID"))
        if not site_id or not project_id:
            skipped += 1
            row_errors[int(idx) + 2] = ["SITE_ID and PROJECT_ID are required"]
            continue

        key = (site_id, project_id)
        if key in seen_keys:
            row_errors[int(idx) + 2] = [
                f"Duplicate (SITE_ID, PROJECT_ID) = ({site_id}, {project_id}) in this upload"
            ]
            skipped += 1
            continue
        seen_keys.add(key)

        payload, errs = _build_milestone_payload(row, df_columns, schema)
        if errs:
            row_errors[int(idx) + 2] = errs
            skipped += 1
            continue

        parsed_rows.append({
            "site_id": site_id,
            "project_id": project_id,
            "region": _clean_text(row.get("REGION")),
            "market": _clean_text(row.get("MARKET")),
            "milestone_actuals": payload,
        })

    if row_errors:
        return {
            "ok": False,
            "inserted": 0,
            "skipped": skipped,
            "row_errors": row_errors,
        }

    # Replace: delete previous user rows, insert fresh set
    db.query(MacroMilestoneUploadedData).filter(
        MacroMilestoneUploadedData.user_id == uploaded_by
    ).delete(synchronize_session=False)

    for r in parsed_rows:
        db.add(MacroMilestoneUploadedData(
            user_id=uploaded_by,
            site_id=r["site_id"],
            project_id=r["project_id"],
            region=r["region"],
            market=r["market"],
            milestone_actuals=json.dumps(r["milestone_actuals"]),
        ))

    db.commit()
    return {
        "ok": True,
        "inserted": len(parsed_rows),
        "skipped": skipped,
    }


# ----------------------------------------------------------------
# Readers
# ----------------------------------------------------------------

def list_user_uploads(db: Session, user_id: str) -> list[dict]:
    """Return all milestone-upload rows for a user (latest snapshot)."""
    rows = (
        db.query(MacroMilestoneUploadedData)
        .filter(MacroMilestoneUploadedData.user_id == user_id)
        .order_by(MacroMilestoneUploadedData.site_id)
        .all()
    )
    out = []
    for r in rows:
        try:
            payload = json.loads(r.milestone_actuals) if r.milestone_actuals else {}
        except (json.JSONDecodeError, ValueError, TypeError):
            payload = {}
        out.append({
            "id": r.id,
            "user_id": r.user_id,
            "site_id": r.site_id,
            "project_id": r.project_id,
            "region": r.region,
            "market": r.market,
            "milestone_actuals": payload,
            "created_at": str(r.created_at) if r.created_at else None,
            "updated_at": str(r.updated_at) if r.updated_at else None,
        })
    return out


def delete_user_uploads(db: Session, user_id: str) -> int:
    """Delete all milestone-upload rows for a user. Returns rows deleted."""
    n = (
        db.query(MacroMilestoneUploadedData)
        .filter(MacroMilestoneUploadedData.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return n
