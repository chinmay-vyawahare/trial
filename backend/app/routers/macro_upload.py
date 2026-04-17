"""
Excel Upload Router (unified for macro + ahloa).

Upload CSV/Excel files with planned CX start dates.
project_type distinguishes macro vs ahloa uploads.
"""

import logging
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_config_db
from app.models.prerequisite import MacroUploadedData
from app.services.macro_upload import parse_upload_file, upsert_uploaded_data

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/excel-upload",
    tags=["excel-upload"],
)


@router.post("/upload")
async def upload_data(
    user_id: str = Query(..., description="User ID performing the upload"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    file: UploadFile = File(...),
    db: Session = Depends(get_config_db),
):
    """
    Upload a CSV or Excel file with planned CX start dates.

    Expected columns: SITE_ID, REGION, MARKET, PROJECT_ID, pj_p_4225_construction_start_finish
    Works for both macro and ahloa project types.
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

    result = upsert_uploaded_data(db, df, uploaded_by=user_id, project_type=project_type)

    return {
        "message": "Upload successful",
        "filename": file.filename,
        "project_type": project_type,
        **result,
    }


@router.get("")
def list_uploaded_data(
    user_id: str = Query(..., description="User ID to filter uploaded data"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """List all planned dates uploaded by a user, filtered by project_type."""
    rows = (
        db.query(MacroUploadedData)
        .filter(
            MacroUploadedData.uploaded_by == user_id,
            MacroUploadedData.project_type == project_type,
        )
        .order_by(MacroUploadedData.site_id)
        .all()
    )

    return {
        "project_type": project_type,
        "total": len(rows),
        "data": [
            {
                "id": r.id,
                "site_id": r.site_id,
                "region": r.region,
                "market": r.market,
                "project_id": r.project_id,
                "pj_p_4225_construction_start_finish": str(r.pj_p_4225_construction_start_finish) if r.pj_p_4225_construction_start_finish else None,
                "uploaded_by": r.uploaded_by,
                "project_type": r.project_type,
                "created_at": str(r.created_at) if r.created_at else None,
                "updated_at": str(r.updated_at) if r.updated_at else None,
            }
            for r in rows
        ],
    }


@router.delete("")
def delete_uploaded_data(
    user_id: str = Query(..., description="User ID whose data to delete"),
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """Delete all planned dates uploaded by a user for a project_type."""
    count = (
        db.query(MacroUploadedData)
        .filter(
            MacroUploadedData.uploaded_by == user_id,
            MacroUploadedData.project_type == project_type,
        )
        .delete()
    )
    db.commit()
    return {"message": f"Deleted {count} rows for user {user_id} project_type={project_type}"}
