"""
Persist AI-extracted per-site Excel notes into ai_based_excel_upload.

Workflow:
  1. process_excel(file_path) -> DataFrame[SITE_ID, (PROJECT_ID), REGION, MARKET,
                                           forecasted_cx_start_date, is_blocked, blocked_reason]
  2. ingest_ai_excel(file_bytes, filename, db, uploaded_by) — saves the DataFrame
     rows into AIBasedExcelUpload (replace-on-upload per user) and returns a
     summary used for the assistant chat confirmation message.
"""

import io
import os
import tempfile
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models.prerequisite import AIBasedExcelUpload
from app.services.excel_through_ai import process_excel


def _parse_date(val) -> datetime | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def ingest_ai_excel(
    file_bytes: bytes,
    filename: str,
    db: Session,
    uploaded_by: str,
) -> dict:
    """
    Save uploaded bytes to a temp file, run the AI extractor, and replace this
    user's existing AI rows with the freshly-extracted ones.

    Returns a dict suitable for building the chat confirmation message:
        {
          "ok": True,
          "filename": str,
          "n_sites": int,
          "sites": [{site_id, project_id, forecasted_cx_start_date, is_blocked, blocked_reason}, ...],
        }
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        df = process_excel(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Replace this user's AI rows entirely (latest upload wins).
    db.query(AIBasedExcelUpload).filter(
        AIBasedExcelUpload.uploaded_by == uploaded_by
    ).delete(synchronize_session=False)

    has_project = "PROJECT_ID" in df.columns
    summary_rows: list[dict] = []
    inserted = 0

    for _, row in df.iterrows():
        site_id = str(row.get("SITE_ID") or "").strip()
        if not site_id:
            continue

        project_id = (
            str(row.get("PROJECT_ID") or "").strip() if has_project else ""
        ) or None

        cx = _parse_date(row.get("forecasted_cx_start_date"))
        is_blocked = bool(row.get("is_blocked"))
        blocked_reason = (
            str(row.get("blocked_reason") or "").strip() if row.get("blocked_reason") else None
        )

        db.add(
            AIBasedExcelUpload(
                site_id=site_id,
                project_id=project_id,
                region=str(row.get("REGION") or "").strip() or None,
                market=str(row.get("MARKET") or "").strip() or None,
                forecasted_cx_start_date=cx,
                is_blocked=is_blocked,
                blocked_reason=blocked_reason,
                uploaded_by=uploaded_by,
            )
        )
        inserted += 1
        summary_rows.append({
            "site_id": site_id,
            "project_id": project_id,
            "forecasted_cx_start_date": cx.date().isoformat() if cx else None,
            "is_blocked": is_blocked,
            "blocked_reason": blocked_reason,
        })

    db.commit()

    return {
        "ok": True,
        "filename": filename,
        "n_sites": inserted,
        "sites": summary_rows,
    }


def build_summary_message(result: dict) -> str:
    """Build a short markdown-ish confirmation for the assistant chat reply."""
    n = result.get("n_sites", 0)
    sites = result.get("sites", [])
    lines = [
        f"Extracted forecasted CX dates from `{result.get('filename')}` for {n} site(s).",
        "Dashboards will reflect these dates on the next refresh.",
        "",
    ]
    for s in sites[:10]:
        cx = s.get("forecasted_cx_start_date") or "—"
        suffix = ""
        if s.get("is_blocked"):
            reason = s.get("blocked_reason") or "blocked"
            suffix = f" (blocked: {reason})"
        proj = f" / {s['project_id']}" if s.get("project_id") else ""
        lines.append(f"- {s['site_id']}{proj}: CX {cx}{suffix}")
    if n > 10:
        lines.append(f"… and {n - 10} more.")
    return "\n".join(lines)
