"""
User History SLA Days endpoints.

- GET  /history-sla-days/{user_id}  — get all history expected days for a user
- POST /history-sla-days/reset      — clear history expected days for a user (or all users)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_config_db
from app.models.prerequisite import UserHistoryExpectedDays
from app.schemas.gantt import UserHistoryExpectedDaysOut

router = APIRouter(
    prefix="/api/v1/schedular/history-sla-days",
    tags=["history-sla-days"],
)


@router.get("/{user_id}", response_model=list[UserHistoryExpectedDaysOut])
def get_user_history_expected_days(
    user_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Return all history_expected_days entries for a user."""
    return (
        config_db.query(UserHistoryExpectedDays)
        .filter(UserHistoryExpectedDays.user_id == user_id)
        .all()
    )


@router.post("/reset")
def reset_history_sla_days(
    user_id: str = Query(None, description="User ID to reset for. If omitted, resets for all users."),
    config_db: Session = Depends(get_config_db),
):
    """Clear history_expected_days for a user (or all users)."""
    query = config_db.query(UserHistoryExpectedDays)
    if user_id:
        query = query.filter(UserHistoryExpectedDays.user_id == user_id)

    deleted = query.delete()
    config_db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="No history SLA values found to reset")
    scope = f"user '{user_id}'" if user_id else "all users"
    return {"detail": f"Reset history_expected_days for {deleted} milestones ({scope})"}
