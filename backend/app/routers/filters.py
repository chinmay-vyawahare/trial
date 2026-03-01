from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.gantt import get_filter_options

router = APIRouter(prefix="/api/v1/schedular/filters", tags=["filters"])

@router.get("/regions")
def get_regions(db: Session = Depends(get_db)):
    filters = get_filter_options(db)
    return filters.get("regions", [])

@router.get("/markets")
def get_markets(db: Session = Depends(get_db)):
    filters = get_filter_options(db)
    return filters.get("markets", [])

@router.get("/sites")
def get_sites(db: Session = Depends(get_db)):
    filters = get_filter_options(db)
    return filters.get("site_ids", [])

@router.get("/vendors")
def get_vendors(db: Session = Depends(get_db)):
    filters = get_filter_options(db)
    return filters.get("vendors", [])
