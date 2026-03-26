"""
Export endpoints.

GET /api/v1/schedular/export/gantt-csv           — default / user-override SLA export
GET /api/v1/schedular/export/gantt-csv-history    — SLA history-based export
"""

import logging
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.database import get_db, get_config_db
from app.services.export import export_gantt_csv, export_gantt_csv_history

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/export",
    tags=["export"],
)


@router.get("/gantt-csv")
def export_gantt_to_csv(
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID — if provided, applies user's saved filters. If not, exports all sites."),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    status: str = Query(None, description="Filter by overall_status"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
    sla_type: str = Query("default", description="SLA type to use: 'default' or 'user_based' (requires user_id)"),
):
    """
    Export gantt chart data as a downloadable CSV file.

    - With user_id: applies that user's saved filters
    - Without user_id: exports all sites (no filters)
    - Supports all gantt chart filters (region, market, vendor, etc.)
    """
    try:
        csv_content = export_gantt_csv(
            db=db,
            config_db=config_db,
            user_id=user_id.strip() if user_id else None,
            region=region,
            market=market,
            site_id=site_id,
            vendor=vendor,
            area=area,
            consider_vendor_capacity=consider_vendor_capacity,
            pace_constraint_flag=pace_constraint_flag,
            status=status,
            sla_type=sla_type,
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


@router.get("/gantt-csv-history")
def export_gantt_to_csv_history(
    date_from: str = Query(..., description="History date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="History date range end (YYYY-MM-DD)"),
    region: list[str] = Query(None, description="Filter by region (multi-value)"),
    market: list[str] = Query(None, description="Filter by market (multi-value)"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    area: list[str] = Query(None, description="Filter by area (multi-value)"),
    user_id: str = Query(None, description="User ID — if provided, applies user's saved filters."),
    consider_vendor_capacity: bool = Query(False, description="Apply GC vendor capacity constraints"),
    pace_constraint_flag: bool = Query(False, description="Apply pace constraints for the user"),
    status: str = Query(None, description="Filter by overall_status or exclude_reason"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Export gantt chart data as CSV using SLA history-based expected_days.

    Computes expected_days from historical actual dates within [date_from, date_to].
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    try:
        csv_content = export_gantt_csv_history(
            db=db,
            config_db=config_db,
            date_from=df,
            date_to=dt,
            user_id=user_id.strip() if user_id else None,
            region=region,
            market=market,
            site_id=site_id,
            vendor=vendor,
            area=area,
            consider_vendor_capacity=consider_vendor_capacity,
            pace_constraint_flag=pace_constraint_flag,
            status=status,
        )
    except Exception as e:
        logger.exception(f"Failed to export SLA history gantt CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate SLA history CSV export.")

    filename = f"gantt_chart_history_{date_from}_{date_to}.csv"

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
