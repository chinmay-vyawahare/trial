"""
Skip-prerequisite APIs (unified for macro + ahloa).

When a user skips a prerequisite the planned-date calculation treats that
milestone as having zero duration (instantly complete).

project_type='macro': uses UserSkippedPrerequisite + MilestoneDefinition
project_type='ahloa': uses AhloaUserSkippedPrerequisite + AhloaMilestoneDefinition
  (AHLOA also supports market-wise skip via optional market param)

- POST   /skip-prerequisites                           — skip a prerequisite for a user
- GET    /skip-prerequisites/{user_id}                 — list skipped prerequisites for a user
- DELETE /skip-prerequisites/{user_id}/{milestone_key} — un-skip a single prerequisite
- DELETE /skip-prerequisites/{user_id}                 — un-skip all prerequisites for a user
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import UserSkippedPrerequisite, MilestoneDefinition
from app.models.ahloa import AhloaMilestoneDefinition, AhloaUserSkippedPrerequisite

router = APIRouter(
    prefix="/api/v1/schedular/skip-prerequisites",
    tags=["skip-prerequisites"],
)


class SkipRequest(BaseModel):
    user_id: str
    milestone_key: str
    market: str | None = None
    area: str | None = None


def _validate_single_geo_level(market: str | None, area: str | None):
    """Reject if both market AND area are set — only one geo level per skip."""
    if market and market.strip() and area and area.strip():
        raise HTTPException(
            status_code=400,
            detail="Only one geo level (market OR area) can be set per skip.",
        )


@router.post("")
def skip_prerequisite(
    body: SkipRequest,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """Skip a prerequisite for a user. AHLOA supports optional market OR area scope."""
    if project_type == "ahloa":
        ms = db.query(AhloaMilestoneDefinition).filter(AhloaMilestoneDefinition.key == body.milestone_key).first()
        if not ms:
            raise HTTPException(404, f"AHLOA milestone '{body.milestone_key}' not found")

        _validate_single_geo_level(body.market, body.area)

        # Reject duplicate: same (user, milestone, market) or (user, milestone, area).
        # NULL participates as a real value here — i.e. (market=null, area=null) global
        # skip conflicts only with another (market=null, area=null) row.
        new_market = (body.market or None) if (body.market and body.market.strip()) else None
        new_area = (body.area or None) if (body.area and body.area.strip()) else None

        existing = (
            db.query(AhloaUserSkippedPrerequisite)
            .filter(
                AhloaUserSkippedPrerequisite.user_id == body.user_id,
                AhloaUserSkippedPrerequisite.milestone_key == body.milestone_key,
                AhloaUserSkippedPrerequisite.market.is_(new_market) if new_market is None
                else AhloaUserSkippedPrerequisite.market == new_market,
                AhloaUserSkippedPrerequisite.area.is_(new_area) if new_area is None
                else AhloaUserSkippedPrerequisite.area == new_area,
            )
            .first()
        )
        if existing:
            scope = (
                f"market '{new_market}'" if new_market
                else f"area '{new_area}'" if new_area
                else "all markets"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Prerequisite '{body.milestone_key}' is already skipped for {scope}.",
            )

        row = AhloaUserSkippedPrerequisite(
            user_id=body.user_id,
            milestone_key=body.milestone_key,
            market=new_market,
            area=new_area,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id, "user_id": row.user_id, "milestone_key": row.milestone_key,
            "market": row.market, "area": row.area, "project_type": "ahloa",
        }
    else:
        ms = db.query(MilestoneDefinition).filter(MilestoneDefinition.key == body.milestone_key).first()
        if not ms:
            raise HTTPException(404, f"Milestone '{body.milestone_key}' not found")

        existing = (
            db.query(UserSkippedPrerequisite)
            .filter(UserSkippedPrerequisite.user_id == body.user_id, UserSkippedPrerequisite.milestone_key == body.milestone_key)
            .first()
        )
        if existing:
            return {"id": existing.id, "user_id": existing.user_id, "milestone_key": existing.milestone_key, "project_type": "macro"}

        row = UserSkippedPrerequisite(user_id=body.user_id, milestone_key=body.milestone_key)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "user_id": row.user_id, "milestone_key": row.milestone_key, "project_type": "macro"}


@router.get("/{user_id}")
def list_skipped_prerequisites(
    user_id: str,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    market: str = Query(None, description="Filter by market (AHLOA only)"),
    area: str = Query(None, description="Filter by area (AHLOA only)"),
    db: Session = Depends(get_config_db),
):
    """Return all skipped prerequisites for a user, filtered by project_type."""
    if project_type == "ahloa":
        q = db.query(AhloaUserSkippedPrerequisite).filter(AhloaUserSkippedPrerequisite.user_id == user_id)
        if market:
            q = q.filter(AhloaUserSkippedPrerequisite.market == market)
        if area:
            q = q.filter(AhloaUserSkippedPrerequisite.area == area)
        rows = q.all()
        return [
            {
                "id": r.id, "user_id": r.user_id, "milestone_key": r.milestone_key,
                "market": r.market, "area": r.area, "project_type": "ahloa",
            }
            for r in rows
        ]
    else:
        rows = db.query(UserSkippedPrerequisite).filter(UserSkippedPrerequisite.user_id == user_id).all()
        return [{"id": r.id, "user_id": r.user_id, "milestone_key": r.milestone_key, "project_type": "macro"} for r in rows]


@router.delete("/{user_id}/{milestone_key}")
def unskip_prerequisite(
    user_id: str,
    milestone_key: str,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    market: str = Query(None, description="Market to unskip (AHLOA only)"),
    area: str = Query(None, description="Area to unskip (AHLOA only)"),
    db: Session = Depends(get_config_db),
):
    """Remove a single skipped prerequisite for a user.

    AHLOA: at most one of market/area; if neither, removes the all-markets row.
    """
    if project_type == "ahloa":
        _validate_single_geo_level(market, area)
        q = db.query(AhloaUserSkippedPrerequisite).filter(
            AhloaUserSkippedPrerequisite.user_id == user_id,
            AhloaUserSkippedPrerequisite.milestone_key == milestone_key,
        )
        if market:
            q = q.filter(AhloaUserSkippedPrerequisite.market == market,
                         AhloaUserSkippedPrerequisite.area.is_(None))
        elif area:
            q = q.filter(AhloaUserSkippedPrerequisite.area == area,
                         AhloaUserSkippedPrerequisite.market.is_(None))
        else:
            q = q.filter(AhloaUserSkippedPrerequisite.market.is_(None),
                         AhloaUserSkippedPrerequisite.area.is_(None))
        deleted = q.delete(synchronize_session=False)
    else:
        deleted = (
            db.query(UserSkippedPrerequisite)
            .filter(UserSkippedPrerequisite.user_id == user_id, UserSkippedPrerequisite.milestone_key == milestone_key)
            .delete()
        )

    db.commit()
    if deleted == 0:
        raise HTTPException(404, f"Skip entry not found for user '{user_id}', milestone '{milestone_key}'")
    return {"detail": f"Un-skipped '{milestone_key}' for user '{user_id}'", "deleted": deleted}


@router.delete("/{user_id}")
def unskip_all_prerequisites(
    user_id: str,
    project_type: str = Query("macro", description="Project type: 'macro' or 'ahloa'"),
    db: Session = Depends(get_config_db),
):
    """Remove all skipped prerequisites for a user."""
    if project_type == "ahloa":
        deleted = db.query(AhloaUserSkippedPrerequisite).filter(AhloaUserSkippedPrerequisite.user_id == user_id).delete(synchronize_session=False)
    else:
        deleted = db.query(UserSkippedPrerequisite).filter(UserSkippedPrerequisite.user_id == user_id).delete()
    db.commit()
    if deleted == 0:
        raise HTTPException(404, f"No skip entries found for user '{user_id}'")
    return {"detail": f"All skip entries cleared for user '{user_id}', removed {deleted} entries"}
