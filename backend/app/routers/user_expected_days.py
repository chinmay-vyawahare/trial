"""
User-level SLA overrides for milestone expected_days.
Supports both macro (UserExpectedDays) and ahloa (AhloaUserExpectedDays) via project_type.

- PUT    /user-expected-days/{user_id}                 — set/update
- GET    /user-expected-days/{user_id}                 — list overrides
- DELETE /user-expected-days/{user_id}/{milestone_key} — delete override
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import UserExpectedDays, MilestoneDefinition

router = APIRouter(
    prefix="/api/v1/schedular/user-expected-days",
    tags=["user-expected-days"],
)


def _get_model(project_type):
    if project_type == "ahloa":
        from app.models.ahloa import AhloaUserExpectedDays
        return AhloaUserExpectedDays
    return UserExpectedDays


def _validate_milestone(db, milestone_key, project_type):
    if project_type == "ahloa":
        from app.models.ahloa import AhloaMilestoneDefinition
        if not db.query(AhloaMilestoneDefinition).filter(AhloaMilestoneDefinition.key == milestone_key).first():
            raise HTTPException(404, f"AHLOA milestone '{milestone_key}' not found")
    else:
        if not db.query(MilestoneDefinition).filter(MilestoneDefinition.key == milestone_key).first():
            raise HTTPException(404, f"Milestone '{milestone_key}' not found")


def _row_to_dict(row, project_type):
    d = {"id": row.id, "user_id": row.user_id, "milestone_key": row.milestone_key,
         "expected_days": row.expected_days, "project_type": project_type}
    if hasattr(row, "back_days"):
        d["back_days"] = row.back_days
    return d


@router.put("/{user_id}")
def set_expected_days(
    user_id: str,
    body: dict,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """Set or update expected_days for a milestone. Supports project_type=ahloa."""
    milestone_key = body.get("milestone_key")
    expected_days = body.get("expected_days")
    back_days = body.get("back_days")

    if not milestone_key:
        raise HTTPException(400, "milestone_key is required")
    if expected_days is None and back_days is None:
        raise HTTPException(400, "At least one of expected_days or back_days must be provided")

    _validate_milestone(db, milestone_key, project_type)
    Model = _get_model(project_type)

    existing = (
        db.query(Model)
        .filter(Model.user_id == user_id, Model.milestone_key == milestone_key)
        .first()
    )
    if existing:
        if expected_days is not None:
            existing.expected_days = expected_days
        if back_days is not None and hasattr(existing, "back_days"):
            existing.back_days = back_days
        db.commit()
        db.refresh(existing)
        return _row_to_dict(existing, project_type)

    kwargs = {"user_id": user_id, "milestone_key": milestone_key, "expected_days": expected_days}
    if project_type == "macro" and back_days is not None:
        kwargs["back_days"] = back_days
    row = Model(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row, project_type)


@router.get("/{user_id}")
def list_expected_days(
    user_id: str,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """List all expected_days overrides for a user."""
    Model = _get_model(project_type)
    rows = db.query(Model).filter(Model.user_id == user_id).all()
    return [_row_to_dict(r, project_type) for r in rows]


@router.delete("/{user_id}/{milestone_key}")
def delete_expected_days(
    user_id: str,
    milestone_key: str,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """Delete a single expected_days override."""
    Model = _get_model(project_type)
    row = db.query(Model).filter(Model.user_id == user_id, Model.milestone_key == milestone_key).first()
    if not row:
        raise HTTPException(404, f"No override found for user '{user_id}', milestone '{milestone_key}'")
    db.delete(row)
    db.commit()
    return {"detail": "Override deleted"}
