"""
Per-user Pace Constraint CRUD endpoints.

Each user manages their own pace constraints that control how many sites
can START within a date range for a given market/area/region scope.

- GET    /pace-constraints?user_id=...        — list user's entries
- POST   /pace-constraints                    — create new entry
- PUT    /pace-constraints/{id}?user_id=...  — update entry
- DELETE /pace-constraints/{id}?user_id=...  — delete entry
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import PaceConstraint
from app.schemas.gantt import PaceConstraintOut, PaceConstraintCreate, PaceConstraintUpdate

router = APIRouter(
    prefix="/api/v1/schedular/pace-constraints",
    tags=["pace-constraints"],
)


@router.get("", response_model=list[PaceConstraintOut])
def list_pace_constraints(
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_config_db),
):
    """List all pace constraints for a user."""
    return (
        db.query(PaceConstraint)
        .filter(PaceConstraint.user_id == user_id)
        .order_by(PaceConstraint.start_date)
        .all()
    )


@router.post("", response_model=PaceConstraintOut)
def create_pace_constraint(body: PaceConstraintCreate, db: Session = Depends(get_config_db)):
    """Create a new pace constraint for a user."""
    try:
        sd = datetime.fromisoformat(body.start_date)
        ed = datetime.fromisoformat(body.end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if sd > ed:
        raise HTTPException(status_code=400, detail="start_date must be before end_date.")

    row = PaceConstraint(
        user_id=body.user_id,
        start_date=sd,
        end_date=ed,
        market=body.market,
        area=body.area,
        region=body.region,
        max_sites=body.max_sites,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{entry_id}", response_model=PaceConstraintOut)
def update_pace_constraint(
    entry_id: int,
    body: PaceConstraintUpdate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_config_db),
):
    """Update a pace constraint (must belong to user)."""
    row = (
        db.query(PaceConstraint)
        .filter(PaceConstraint.id == entry_id, PaceConstraint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Pace constraint {entry_id} not found")

    updates = body.model_dump(exclude_unset=True)

    for date_field in ("start_date", "end_date"):
        if date_field in updates and updates[date_field] is not None:
            try:
                updates[date_field] = datetime.fromisoformat(updates[date_field])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {date_field} format. Use YYYY-MM-DD.")

    for field, value in updates.items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{entry_id}")
def delete_pace_constraint(
    entry_id: int,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_config_db),
):
    """Delete a pace constraint (must belong to user)."""
    row = (
        db.query(PaceConstraint)
        .filter(PaceConstraint.id == entry_id, PaceConstraint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Pace constraint {entry_id} not found")

    db.delete(row)
    db.commit()
    return {"detail": f"Deleted pace constraint {entry_id}"}
