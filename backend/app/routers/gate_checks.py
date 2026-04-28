"""
Gate check endpoints.

GET  endpoints return the distinct lookup values for por_plan_type and
     por_regional_dev_initiatives from the staging table.

POST endpoint saves a user's gate check selections to user_filters.
GET  /{user_id} retrieves the saved gate checks for a user.
"""

import json
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db, STAGING_TABLE
from app.models.prerequisite import UserFilter

router = APIRouter(prefix="/api/v1/schedular/gate-checks", tags=["gate-checks"])

_MACRO_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)

_AHLOA_BASE_WHERE = (
    "pj_hard_cost_vendor_assignment_po ILIKE '%NOKIA%' "
    "AND por_release_version = 'Radio Upgrade NR' "
    "AND por_plan_added_date > '2025-03-28' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)


def _base_where_for(project_type: str) -> str:
    """Pick the staging-row filter clause for the given project_type."""
    pt = (project_type or "macro").strip().lower()
    if pt == "ahloa":
        return _AHLOA_BASE_WHERE
    if pt == "macro":
        return _MACRO_BASE_WHERE
    raise HTTPException(status_code=400, detail="project_type must be 'macro' or 'ahloa'.")


# ----------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------

class GateCheckSave(BaseModel):
    user_id: str
    plan_type_include: Optional[list[str]] = None          # e.g. ["New Build", "FOA"]
    regional_dev_initiatives: Optional[str] = None         # free-text ILIKE pattern


class GateCheckOut(BaseModel):
    user_id: str
    plan_type_include: Optional[list[str]] = None
    regional_dev_initiatives: Optional[str] = None


# ----------------------------------------------------------------
# Lookup endpoints (global distinct values)
# ----------------------------------------------------------------

@router.get("/por_plan_type")
def get_por_plan_type(
    project_type: str = Query("macro", description="'macro' (default) or 'ahloa'"),
    db: Session = Depends(get_db),
):
    """Return all distinct por_plan_type values for the given project_type."""
    base_where = _base_where_for(project_type)
    q = text(
        f"""
        SELECT DISTINCT por_plan_type
        FROM {STAGING_TABLE}
        WHERE {base_where} AND por_plan_type IS NOT NULL
        ORDER BY por_plan_type
        """
    )
    return [r[0] for r in db.execute(q)]


@router.get("/por_regional_dev_initiatives")
def get_por_regional_dev_initiatives(
    project_type: str = Query("macro", description="'macro' (default) or 'ahloa'"),
    db: Session = Depends(get_db),
):
    """Return all distinct por_regional_dev_initiatives values for the given project_type."""
    base_where = _base_where_for(project_type)
    q = text(
        f"""
        SELECT DISTINCT por_regional_dev_initiatives
        FROM {STAGING_TABLE}
        WHERE {base_where} AND por_regional_dev_initiatives IS NOT NULL
        ORDER BY por_regional_dev_initiatives
        """
    )
    return [r[0] for r in db.execute(q)]


# ----------------------------------------------------------------
# User gate check save / get
# ----------------------------------------------------------------

@router.post("", response_model=GateCheckOut)
def save_gate_checks(
    body: GateCheckSave,
    config_db: Session = Depends(get_config_db),
):
    """Save or update gate check selections for a user."""
    if not body.user_id or not body.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    pti_json = json.dumps(body.plan_type_include) if body.plan_type_include else None

    existing = (
        config_db.query(UserFilter)
        .filter(UserFilter.user_id == body.user_id)
        .first()
    )

    if existing:
        existing.plan_type_include = pti_json
        existing.regional_dev_initiatives = body.regional_dev_initiatives
    else:
        config_db.add(UserFilter(
            user_id=body.user_id,
            plan_type_include=pti_json,
            regional_dev_initiatives=body.regional_dev_initiatives,
        ))

    config_db.commit()

    return GateCheckOut(
        user_id=body.user_id,
        plan_type_include=body.plan_type_include,
        regional_dev_initiatives=body.regional_dev_initiatives,
    )


@router.get("/{user_id}", response_model=GateCheckOut)
def get_gate_checks(
    user_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Return saved gate checks for a user."""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    row = (
        config_db.query(UserFilter)
        .filter(UserFilter.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No gate checks found for user '{user_id}'")

    plan_type_include = None
    if row.plan_type_include:
        try:
            plan_type_include = json.loads(row.plan_type_include)
        except (json.JSONDecodeError, TypeError):
            pass

    return GateCheckOut(
        user_id=row.user_id,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=row.regional_dev_initiatives,
    )
