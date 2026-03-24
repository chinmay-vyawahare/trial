"""
User filter management APIs.

Filters are stored column-wise (region, market, vendor, site_id, area,
plan_type_include, regional_dev_initiatives) — one row per user.
Saving filters for the same user_id always upserts (updates the existing
row instead of creating duplicates).

- POST   /user-filters               — save / update filters for a user
- GET    /user-filters/{user_id}     — get saved filters for a user
- DELETE /user-filters/{user_id}     — clear (delete) filters for a user
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import UserFilter
from app.schemas.gantt import UserFilterSave, UserFilterOut

router = APIRouter(
    prefix="/api/v1/schedular/user-filters",
    tags=["user-filters"],
)

@router.get("/{user_id}", response_model=UserFilterOut)
def get_user_filters(user_id: str, db: Session = Depends(get_config_db)):
    """Return saved filters for a user, or empty defaults if none exist."""
    row = db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
    if not row:
        return UserFilterOut(id=0, user_id=user_id)
    return row

@router.delete("/{user_id}")
def clear_user_filters(user_id: str, db: Session = Depends(get_config_db)):
    """Delete all saved filters for a user."""
    deleted = (
        db.query(UserFilter)
        .filter(UserFilter.user_id == user_id)
        .delete()
    )
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No filters found for user '{user_id}'")
    return {"detail": f"Filters cleared for user '{user_id}'"}
