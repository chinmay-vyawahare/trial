"""
Macro Milestone Actual Upload Router.

User-scoped upload of per-milestone actual dates per site+project. Each upload
fully replaces the user's previous payload — only the latest upload is kept.

Endpoints
---------
POST   /macro/milestone-actual-upload/upload     — upload CSV/Excel
GET    /macro/milestone-actual-upload            — get latest upload by user
DELETE /macro/milestone-actual-upload            — clear user's upload
"""

import logging
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_config_db
from app.services.macro_milestone_upload import (
    parse_upload_file,
    replace_uploaded_data,
    list_user_uploads,
    delete_user_uploads,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/macro/milestone-actual-upload",
    tags=["macro-milestone-upload"],
)


_MAX_USER_ID = 100


def _require_user_id(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id must not be empty")
    if len(uid) > _MAX_USER_ID:
        raise HTTPException(
            status_code=400,
            detail=f"user_id too long (max {_MAX_USER_ID} chars)",
        )
    return uid


@router.post("/upload")
async def upload_milestone_actuals(
    user_id: str = Query(..., description="User ID performing the upload"),
    file: UploadFile = File(...),
    db: Session = Depends(get_config_db),
):
    user_id = _require_user_id(user_id)
    """
    Upload a CSV or Excel file with per-milestone actual dates per site+project.

    Required columns: SITE_ID, PROJECT_ID
    Optional metadata: REGION, MARKET
    Milestone columns: must match MilestoneDefinition.name (case-insensitive).
        - Date milestones (e.g. "Entitlement Complete (MS 3710)"): date in M/D/YYYY
        - Text milestones (e.g. "CPO Available"): free text
        - With-status milestones (e.g. "Steel Received (If applicable)"):
            pair a date column with a "{name} - Status" column whose value
            must be one of: A, N, Not Applicable, or blank.

    This upload FULLY REPLACES the user's previous payload.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        df = parse_upload_file(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if df.empty:
        raise HTTPException(status_code=400, detail="File has no data rows")

    result = replace_uploaded_data(db, df, uploaded_by=user_id)

    if not result.get("ok"):
        return {
            "message": "Upload failed validation — nothing persisted",
            "filename": file.filename,
            **result,
        }

    return {
        "message": "Upload successful",
        "filename": file.filename,
        **result,
    }


@router.get("")
def get_milestone_actuals(
    user_id: str = Query(..., description="User ID to fetch uploaded data for"),
    db: Session = Depends(get_config_db),
):
    """Return the user's latest milestone-actual upload."""
    user_id = _require_user_id(user_id)
    rows = list_user_uploads(db, user_id)
    return {"user_id": user_id, "total": len(rows), "data": rows}


@router.delete("")
def delete_milestone_actuals(
    user_id: str = Query(..., description="User ID whose data to delete"),
    db: Session = Depends(get_config_db),
):
    """Delete all milestone-actual upload rows for the user."""
    user_id = _require_user_id(user_id)
    n = delete_user_uploads(db, user_id)
    return {"message": f"Deleted {n} rows for user {user_id}", "deleted": n}
