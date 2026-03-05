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
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.models.prerequisite import UserFilter

router = APIRouter(prefix="/api/v1/schedular/gate-checks", tags=["gate-checks"])

_BASE_WHERE = (
    "smp_name = 'NTM'"
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)


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
def get_por_plan_type(db: Session = Depends(get_db)):
    """Return all distinct por_plan_type values."""
    q = text(
        f"""
        SELECT DISTINCT por_plan_type
        FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {_BASE_WHERE} AND por_plan_type IS NOT NULL
        ORDER BY por_plan_type
        """
    )
    return [r[0] for r in db.execute(q)]


@router.get("/por_regional_dev_initiatives")
def get_por_regional_dev_initiatives(db: Session = Depends(get_db)):
    """Return all distinct por_regional_dev_initiatives values."""
    q = text(
        f"""
        SELECT DISTINCT por_regional_dev_initiatives
        FROM public.stg_ndpd_mbt_tmobile_macro_combined
        WHERE {_BASE_WHERE} AND por_regional_dev_initiatives IS NOT NULL
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
