"""
Skip-prerequisite APIs.

When a user skips a prerequisite the planned-date calculation treats that
milestone as having zero duration (instantly complete).  All downstream
milestones are recalculated accordingly.

- POST   /skip-prerequisites                           — skip a prerequisite for a user
- GET    /skip-prerequisites/{user_id}                 — list skipped prerequisites for a user
- DELETE /skip-prerequisites/{user_id}/{milestone_key} — un-skip a single prerequisite
- DELETE /skip-prerequisites/{user_id}                 — un-skip all prerequisites for a user
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import UserSkippedPrerequisite, MilestoneDefinition
from app.schemas.gantt import SkipPrerequisiteRequest, SkipPrerequisiteOut

router = APIRouter(
    prefix="/api/v1/schedular/skip-prerequisites",
    tags=["skip-prerequisites"],
)


@router.post("", response_model=SkipPrerequisiteOut)
def skip_prerequisite(
    body: SkipPrerequisiteRequest,
    db: Session = Depends(get_config_db),
):
    """
    Mark a prerequisite as skipped for a user.

    Validates the milestone_key exists and prevents duplicate entries.
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

    # Prevent duplicate
    existing = (
        db.query(UserSkippedPrerequisite)
        .filter(
            UserSkippedPrerequisite.user_id == body.user_id,
            UserSkippedPrerequisite.milestone_key == body.milestone_key,
        )
        .first()
    )
    if existing:
        return existing

    row = UserSkippedPrerequisite(
        user_id=body.user_id,
        milestone_key=body.milestone_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{user_id}", response_model=list[SkipPrerequisiteOut])
def list_skipped_prerequisites(user_id: str, db: Session = Depends(get_config_db)):
    """Return all skipped prerequisites for a user."""
    rows = (
        db.query(UserSkippedPrerequisite)
        .filter(UserSkippedPrerequisite.user_id == user_id)
        .all()
    )
    return rows


@router.delete("/{user_id}/{milestone_key}")
def unskip_prerequisite(
    user_id: str,
    milestone_key: str,
    db: Session = Depends(get_config_db),
):
    """Remove a single skipped prerequisite for a user."""
    deleted = (
        db.query(UserSkippedPrerequisite)
        .filter(
            UserSkippedPrerequisite.user_id == user_id,
            UserSkippedPrerequisite.milestone_key == milestone_key,
        )
        .delete()
    )
    db.commit()
    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Skip entry not found for user '{user_id}', milestone '{milestone_key}'",
        )
    return {"detail": f"Un-skipped '{milestone_key}' for user '{user_id}'"}


@router.delete("/{user_id}")
def unskip_all_prerequisites(user_id: str, db: Session = Depends(get_config_db)):
    """Remove all skipped prerequisites for a user."""
    deleted = (
        db.query(UserSkippedPrerequisite)
        .filter(UserSkippedPrerequisite.user_id == user_id)
        .delete()
    )
    db.commit()
    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No skip entries found for user '{user_id}'",
        )
    return {"detail": f"All skip entries cleared for user '{user_id}', removed {deleted} entries"}
