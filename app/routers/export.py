"""
Export endpoints.

GET /api/v1/schedular/export/gantt-csv
  - Optional user_id query param
  - If user_id provided: exports gantt chart with that user's saved filters
  - If no user_id: exports full gantt chart (all sites, no filters)
  - Returns a downloadable CSV file
"""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.database import get_db, get_config_db
from app.services.export import export_gantt_csv

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/export",
    tags=["export"],
)


@router.get("/gantt-csv")
def export_gantt_to_csv(
    user_id: str = Query(None, description="User ID — if provided, applies user's saved filters. If not, exports all sites."),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Export gantt chart data as a downloadable CSV file.

    - With user_id: applies that user's saved filters
    - Without user_id: exports all sites (no filters)
    """
    try:
        csv_content = export_gantt_csv(
            db=db,
            config_db=config_db,
            user_id=user_id.strip() if user_id else None,
        )
    except Exception as e:
        logger.exception(f"Failed to export gantt CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate CSV export.")

    # Stream the CSV as a downloadable file
    filename = f"gantt_chart_{user_id}.csv" if user_id else "gantt_chart_all.csv"

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
