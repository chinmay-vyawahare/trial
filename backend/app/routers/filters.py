import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.gantt import get_filter_options, get_region_hierarchy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/schedular/filters", tags=["filters"])


def _safe_get_filter_options(db: Session, key: str, project_type: str = "macro") -> list:
    """Fetch filter options with error handling."""
    try:
        filters = get_filter_options(db, project_type=project_type)
        return filters.get(key, [])
    except Exception as e:
        logger.exception(f"Failed to fetch filter options for '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch {key} from database.")


@router.get("/hierarchy")
def get_hierarchy(
    db: Session = Depends(get_db),
    region: str = None,
    area: str = None,
    market: str = None,
    project_type: str = "macro",
):
    return get_region_hierarchy(db, region, area, market, project_type=project_type)


@router.get("/regions")
def get_regions(db: Session = Depends(get_db)):
    return _safe_get_filter_options(db, "regions")


@router.get("/markets")
def get_markets(db: Session = Depends(get_db)):
    return _safe_get_filter_options(db, "markets")


@router.get("/areas")
def get_areas(db: Session = Depends(get_db)):
    return _safe_get_filter_options(db, "areas")


@router.get("/sites")
def get_sites(db: Session = Depends(get_db), project_type: str = "macro"):
    return _safe_get_filter_options(db, "site_ids", project_type=project_type)


@router.get("/vendors")
def get_vendors(db: Session = Depends(get_db)):
    return _safe_get_filter_options(db, "vendors")
