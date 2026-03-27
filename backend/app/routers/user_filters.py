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

@router.post("", response_model=UserFilterOut)
def save_user_filters(payload: UserFilterSave, db: Session = Depends(get_config_db)):
    """
    Save or update filters for a user.  **Partial update** — only fields
    explicitly included in the request body are changed; omitted fields
    keep their existing DB values.  This lets the assistant send just
    ``{user_id, region: ["Central"]}`` without wiping area/market/etc.
    """
    # Determine which fields the caller actually sent (vs. left out)
    provided = payload.model_fields_set - {"user_id"}

    # Serialize list fields as JSON strings for DB storage
    def _json(val: list | None) -> str | None:
        return json.dumps(val) if val else None

    field_to_value = {
        "region":                   _json(payload.region),
        "market":                   _json(payload.market),
        "area":                     _json(payload.area),
        "plan_type_include":        _json(payload.plan_type_include),
        "vendor":                   payload.vendor,
        "site_id":                  payload.site_id,
        "regional_dev_initiatives": payload.regional_dev_initiatives,
    }

    existing = db.query(UserFilter).filter(UserFilter.user_id == payload.user_id).first()

    if existing:
        # Only touch columns the caller explicitly provided
        for field_name in provided:
            if field_name in field_to_value:
                setattr(existing, field_name, field_to_value[field_name])
        db.commit()
        db.refresh(existing)
        return existing

    # New row — use provided values, everything else stays NULL
    new_row = UserFilter(
        user_id=payload.user_id,
        **{k: v for k, v in field_to_value.items() if k in provided},
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


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
