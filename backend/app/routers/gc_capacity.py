"""
GC Capacity Market Trial — read-only endpoint.

This table is predefined in the public schema and NOT managed by this app.
Only provides a GET endpoint to list entries for reference.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.prerequisite import GcCapacityMarketTrial
from app.schemas.gantt import GcCapacityOut

router = APIRouter(
    prefix="/api/v1/schedular/gc-capacity",
    tags=["gc-capacity"],
)


@router.get("", response_model=list[GcCapacityOut])
def list_gc_capacity(db: Session = Depends(get_db)):
    """List all GC capacity entries (read-only, from public schema)."""
    return (
        db.query(GcCapacityMarketTrial)
        .order_by(GcCapacityMarketTrial.gc_company, GcCapacityMarketTrial.market)
        .all()
    )
