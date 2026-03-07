"""
User-level SLA overrides for milestone expected_days.

Each user can customise the expected_days for any prerequisite.
The override is used in gantt-chart and dashboard calculations instead
of the global MilestoneDefinition.expected_days.

- PUT    /user-expected-days/{user_id}                          — set/update expected_days for a milestone
- GET    /user-expected-days/{user_id}                          — list all overrides for a user
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import UserExpectedDays, MilestoneDefinition
from app.schemas.gantt import UserExpectedDaysRequest, UserExpectedDaysOut

router = APIRouter(
    prefix="/api/v1/schedular/user-expected-days",
    tags=["user-expected-days"],
)


@router.put("/{user_id}", response_model=UserExpectedDaysOut)
def set_expected_days(
    user_id: str,
    body: UserExpectedDaysRequest,
    db: Session = Depends(get_config_db),
):
    """
    Set or update the expected_days for a milestone for this user.

    Creates a new override if one doesn't exist, otherwise updates it.
    """
    # Validate milestone exists
    ms = (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.key == body.milestone_key)
        .first()
    )
    if not ms:
        raise HTTPException(
            status_code=404,
            detail=f"Milestone '{body.milestone_key}' not found",
        )

    if body.expected_days < 0:
        raise HTTPException(
            status_code=400,
            detail="expected_days must be >= 0",
        )

    # Upsert
    existing = (
        db.query(UserExpectedDays)
        .filter(
            UserExpectedDays.user_id == user_id,
            UserExpectedDays.milestone_key == body.milestone_key,
        )
        .first()
    )
    if existing:
        existing.expected_days = body.expected_days
        db.commit()
        db.refresh(existing)
        return existing

    row = UserExpectedDays(
        user_id=user_id,
        milestone_key=body.milestone_key,
        expected_days=body.expected_days,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{user_id}", response_model=list[UserExpectedDaysOut])
def list_expected_days(user_id: str, db: Session = Depends(get_config_db)):
    """Return all expected_days overrides for a user."""
    return (
        db.query(UserExpectedDays)
        .filter(UserExpectedDays.user_id == user_id)
        .all()
    )


