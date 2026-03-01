from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.gantt import (
    get_all_sites_gantt,
    get_dashboard_summary,
    get_filter_options,
)

router = APIRouter(prefix="/api/v1/schedular/gantt-charts", tags=["gantt-charts"])

@router.get("")
def list_sites(
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    site_id: str = Query(None, description="Filter by site ID"),
    vendor: str = Query(None, description="Filter by vendor"),
    limit: int = Query(None, description="Limit the number of results"),
    offset: int = Query(None, description="Offset the results"),
    db: Session = Depends(get_db),
):
    sites, total_count,count = get_all_sites_gantt(
        db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        limit=limit,
        offset=offset,
    )
    return {
        "count": count,
        "sites": sites,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total_count": total_count,
        }
    }


@router.get("/dashboard")
def dashboard(
    region: str = Query(None, description="Filter by region"),
    market: str = Query(None, description="Filter by market"),
    vendor: str = Query(None, description="Filter by vendor"),
    overall_status: str = Query(None, description="Filter by overall status"),
    db: Session = Depends(get_db),
):
    return get_dashboard_summary(
        db,
        region=region,
        market=market,
        vendor=vendor,
        overall_status=overall_status,
    )
