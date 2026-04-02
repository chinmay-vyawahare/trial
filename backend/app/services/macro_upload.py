"""
Macro Planned Date Upload Service

Parses CSV/Excel files and upserts rows into macro_uploaded_data table.
Expected columns: SITE_ID, REGION, MARKET, PROJECT_ID, pj_p_4225_construction_start_finish
"""

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.prerequisite import MacroUploadedData

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = {
    "SITE_ID": "site_id",
    "REGION": "region",
    "MARKET": "market",
    "PROJECT_ID": "project_id",
    "pj_p_4225_construction_start_finish": "pj_p_4225_construction_start_finish",
}


def _parse_date(val) -> datetime | None:
    """Try to parse a date value from various formats."""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, datetime):
        return val
    val_str = str(val).strip()
    if not val_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    return None


def parse_upload_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or Excel file bytes into a DataFrame."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        raise ValueError(f"Unsupported file type: {filename}. Use .csv, .xlsx, or .xls")

    # Normalize column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # Validate required columns
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    return df


def upsert_uploaded_data(db: Session, df: pd.DataFrame, uploaded_by: str) -> dict:
    """
    Upsert rows from DataFrame into macro_uploaded_data.

    If a row with the same site_id and uploaded_by already exists, it is updated.
    Otherwise a new row is inserted.

    Returns summary: {inserted, updated, skipped, total}
    """
    inserted = 0
    updated = 0
    skipped = 0

    for _, row in df.iterrows():
        site_id = str(row.get("SITE_ID", "")).strip()
        if not site_id:
            skipped += 1
            continue

        date_val = _parse_date(row.get("pj_p_4225_construction_start_finish"))

        existing = (
            db.query(MacroUploadedData)
            .filter(MacroUploadedData.site_id == site_id, MacroUploadedData.uploaded_by == uploaded_by)
            .first()
        )

        if existing:
            existing.region = str(row.get("REGION", "")).strip() or existing.region
            existing.market = str(row.get("MARKET", "")).strip() or existing.market
            existing.project_id = str(row.get("PROJECT_ID", "")).strip() or existing.project_id
            existing.pj_p_4225_construction_start_finish = date_val
            updated += 1
        else:
            new_row = MacroUploadedData(
                site_id=site_id,
                region=str(row.get("REGION", "")).strip() or None,
                market=str(row.get("MARKET", "")).strip() or None,
                project_id=str(row.get("PROJECT_ID", "")).strip() or None,
                pj_p_4225_construction_start_finish=date_val,
                uploaded_by=uploaded_by,
            )
            db.add(new_row)
            inserted += 1

    db.commit()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total": inserted + updated,
    }
