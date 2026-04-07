"""
AHLOA Gantt Chart Router

Separate API endpoints for AHLOA project type.
Does not touch any existing NTM/MACRO code.
"""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.gantt_ahloa_construction import get_ahloa_gantt

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/ahloa",
    tags=["ahloa"],
)


@router.get("/gantt-chart-construction")
def ahloa_sites(
    db: Session = Depends(get_db),
    region: list[str] = Query(None),
    market: list[str] = Query(None),
    site_id: str = None,
    vendor: str = None,
    area: list[str] = Query(None),
    limit: int = None,
    offset: int = None,
):
    """
    AHLOA gantt chart — site-wise milestone-wise data.

    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days
    Each milestone status is based on actual vs expected (CX Start + offset).
    """
    sites, total_count, count = get_ahloa_gantt(
        db=db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        limit=limit,
        offset=offset,
    )

    return {
        "total_count": total_count,
        "count": count,
        "sites": sites,
    }


@router.get("/gantt-chart-scope")
def ahloa_sites(
    db: Session = Depends(get_db),
    region: list[str] = Query(None),
    market: list[str] = Query(None),
    site_id: str = None,
    vendor: str = None,
    area: list[str] = Query(None),
    limit: int = None,
    offset: int = None,
):
    """
    AHLOA gantt chart — site-wise milestone-wise data.

    CX Start = Max(pj_p_3710, pj_p_4075) + 50 days
    Each milestone status is based on actual vs expected (CX Start + offset).
    """
    sites, total_count, count = get_ahloa_gantt(
        db=db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        limit=limit,
        offset=offset,
    )

    return {
        "total_count": total_count,
        "count": count,
        "sites": sites,
    }
