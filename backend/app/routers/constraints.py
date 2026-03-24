"""
Constraint threshold CRUD APIs (count-based).

Two constraint_type values:

  "milestone" — site overall status from pending milestone count
  "overall"   — dashboard status from on-track site count

min_value / max_value define count ranges (integers).

- GET    /constraints                          — list all thresholds
- GET    /constraints/milestone                — list milestone-level thresholds only
- GET    /constraints/overall                  — list overall site-level thresholds only
- GET    /constraints/{id}                     — get single threshold by id
- POST   /constraints                          — create a new threshold
- PUT    /constraints/{id}                     — update a threshold
- DELETE /constraints/{id}                     — delete a threshold
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_config_db
from app.models.prerequisite import ConstraintThreshold
from app.schemas.gantt import ConstraintThresholdSchema, ConstraintThresholdCreate, ConstraintThresholdUpdate

router = APIRouter(
    prefix="/api/v1/schedular/constraints",
    tags=["constraints"],
)


@router.get("", response_model=list[ConstraintThresholdSchema])
def list_constraints(db: Session = Depends(get_config_db)):
    """Return all constraint thresholds ordered by type then sort_order."""
    return (
        db.query(ConstraintThreshold)
        .order_by(ConstraintThreshold.constraint_type, ConstraintThreshold.sort_order)
        .all()
    )


@router.get("/milestone", response_model=list[ConstraintThresholdSchema])
def list_milestone_constraints(db: Session = Depends(get_config_db)):
    """Return milestone-level thresholds only."""
    return (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.constraint_type == "milestone")
        .order_by(ConstraintThreshold.sort_order)
        .all()
    )


@router.get("/overall", response_model=list[ConstraintThresholdSchema])
def list_overall_constraints(db: Session = Depends(get_config_db)):
    """Return overall site-level thresholds only."""
    return (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.constraint_type == "overall")
        .order_by(ConstraintThreshold.sort_order)
        .all()
    )


@router.get("/{constraint_id}", response_model=ConstraintThresholdSchema)
def get_constraint(constraint_id: int, db: Session = Depends(get_config_db)):
    row = db.query(ConstraintThreshold).filter(ConstraintThreshold.id == constraint_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Constraint threshold {constraint_id} not found")
    return row


@router.post("", response_model=ConstraintThresholdSchema)
def create_constraint(
    body: ConstraintThresholdCreate,
    db: Session = Depends(get_config_db),
):
    """
    Create a new constraint threshold.

    The id is auto-generated — do not send it in the request body.
    Duplicate entries (same constraint_type + name) are rejected with 409.
    """
    if body.constraint_type not in ("milestone", "overall"):
        raise HTTPException(status_code=400, detail="constraint_type must be 'milestone' or 'overall'.")
    if body.min_value < 0:
        raise HTTPException(status_code=400, detail="min_value must be >= 0.")
    if body.max_value is not None and body.max_value < 0:
        raise HTTPException(status_code=400, detail="max_value must be >= 0.")
    if body.max_value is not None and body.min_value > body.max_value:
        raise HTTPException(status_code=400, detail="min_value cannot be greater than max_value.")
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required and cannot be empty.")
    if not body.color or not body.color.strip():
        raise HTTPException(status_code=400, detail="color is required and cannot be empty.")

    # Check for overlapping ranges within the same constraint_type
    same_type = (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.constraint_type == body.constraint_type)
        .all()
    )
    for existing_row in same_type:
        ex_min = existing_row.min_value
        ex_max = existing_row.max_value
        new_min = body.min_value
        new_max = body.max_value
        # Check overlap: ranges overlap if new_min <= ex_max and new_max >= ex_min
        ex_upper = ex_max if ex_max is not None else float("inf")
        new_upper = new_max if new_max is not None else float("inf")
        if new_min <= ex_upper and new_upper >= ex_min:
            raise HTTPException(
                status_code=409,
                detail=f"Range {new_min}-{new_max} overlaps with existing constraint '{existing_row.name}' ({ex_min}-{ex_max}).",
            )

    # Prevent duplicate (same constraint_type + name)
    existing = (
        db.query(ConstraintThreshold)
        .filter(
            ConstraintThreshold.constraint_type == body.constraint_type,
            ConstraintThreshold.name == body.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Constraint threshold with type='{body.constraint_type}' and name='{body.name}' already exists (id={existing.id})",
        )

    row = ConstraintThreshold(
        constraint_type=body.constraint_type,
        name=body.name,
        status_label=body.status_label,
        color=body.color,
        min_value=body.min_value,
        max_value=body.max_value,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{constraint_id}", response_model=ConstraintThresholdSchema)
def update_constraint(
    constraint_id: int,
    body: ConstraintThresholdUpdate,
    db: Session = Depends(get_config_db),
):
    """Update an existing constraint threshold (partial update)."""
    row = db.query(ConstraintThreshold).filter(ConstraintThreshold.id == constraint_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Constraint threshold {constraint_id} not found")

    updates = body.model_dump(exclude_unset=True)

    # Validate fields
    new_min = updates.get("min_value", row.min_value)
    new_max = updates.get("max_value", row.max_value)
    if new_min is not None and new_min < 0:
        raise HTTPException(status_code=400, detail="min_value must be >= 0.")
    if new_max is not None and new_max < 0:
        raise HTTPException(status_code=400, detail="max_value must be >= 0.")
    if new_min is not None and new_max is not None and new_min > new_max:
        raise HTTPException(status_code=400, detail="min_value cannot be greater than max_value.")

    # Check for overlapping ranges (exclude self)
    same_type = (
        db.query(ConstraintThreshold)
        .filter(
            ConstraintThreshold.constraint_type == row.constraint_type,
            ConstraintThreshold.id != constraint_id,
        )
        .all()
    )
    for existing_row in same_type:
        ex_min = existing_row.min_value
        ex_max = existing_row.max_value
        ex_upper = ex_max if ex_max is not None else float("inf")
        new_upper = new_max if new_max is not None else float("inf")
        if new_min <= ex_upper and new_upper >= ex_min:
            raise HTTPException(
                status_code=409,
                detail=f"Range {new_min}-{new_max} overlaps with existing constraint '{existing_row.name}' ({ex_min}-{ex_max}).",
            )

    for field, value in updates.items():
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{constraint_id}")
def delete_constraint(constraint_id: int, db: Session = Depends(get_config_db)):
    """Delete a constraint threshold."""
    deleted = (
        db.query(ConstraintThreshold)
        .filter(ConstraintThreshold.id == constraint_id)
        .delete()
    )
    db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Constraint threshold {constraint_id} not found")
    return {"detail": f"Constraint threshold {constraint_id} deleted"}
