"""
Dashboard endpoints — lightweight status summaries.

GET /dashboard/summary      — status counts filtered by area, market, region
GET /dashboard/sla-summary  — status counts using SLA history (median) for a date range
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, get_config_db
from app.services.gantt import get_dashboard_summary
from app.services.gantt.milestones import (
    get_user_expected_days_overrides,
)
from app.models.prerequisite import MilestoneDefinition

router = APIRouter(
    prefix="/api/v1/schedular/dashboard",
    tags=["dashboard"],
)


def _get_skipped_keys(config_db: Session) -> set[str]:
    rows = (
        config_db.query(MilestoneDefinition.key)
        .filter(MilestoneDefinition.is_skipped == True)
        .all()
    )
    return {r[0] for r in rows}


@router.get("/summary")
def dashboard_summary(
    area: str = Query(None, description="Filter by area"),
    market: str = Query(None, description="Filter by market"),
    region: str = Query(None, description="Filter by region"),
    user_id: str = Query(None, description="User ID for SLA overrides"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Return dashboard status counts filtered by area, market, region.

    Response:
      - dashboard_status: overall status label
      - on_track_pct: percentage of on-track sites
      - total_sites, on_track_sites, in_progress_sites, critical_sites, blocked_sites
    """
    skipped_keys = _get_skipped_keys(config_db)
    user_ed_overrides = get_user_expected_days_overrides(config_db, user_id) if user_id else {}

    return get_dashboard_summary(
        db,
        config_db,
        region=region,
        market=market,
        area=area,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_ed_overrides,
    )


@router.get("/sla-summary")
def sla_dashboard_summary(
    date_from: str = Query(..., description="SLA history date range start (YYYY-MM-DD)"),
    date_to: str = Query(..., description="SLA history date range end (YYYY-MM-DD)"),
    area: str = Query(None, description="Filter by area"),
    market: str = Query(None, description="Filter by market"),
    region: str = Query(None, description="Filter by region"),
    user_id: str = Query(None, description="User ID for saved filters"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    """
    Dashboard summary using SLA history (median completion days) for a date range.

    Computes milestone expected_days from historical actual dates using median,
    then calculates the dashboard status counts using those SLA values.

    Response:
      - sla_type: "history_median"
      - date_from, date_to: the date range used
      - sla_milestones: per-milestone median completion days + sample counts
      - dashboard_status, on_track_pct, total_sites, on_track_sites,
        in_progress_sites, critical_sites, blocked_sites
    """
    try:
        df = date.fromisoformat(date_from)
        dt = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if df > dt:
        raise HTTPException(status_code=400, detail="date_from must be before date_to.")

    # Compute SLA history using median
    from app.services.sla_history import compute_history_expected_days

    history_results = compute_history_expected_days(db, config_db, df, dt, use_median=True)

    # Build overrides dict from median history
    history_overrides = {}
    for item in history_results:
        if item["history_expected_days"] is not None:
            history_overrides[item["milestone_key"]] = item["history_expected_days"]

    skipped_keys = _get_skipped_keys(config_db)

    # Get dashboard summary using history-based SLA overrides
    summary = get_dashboard_summary(
        db,
        config_db,
        region=region,
        market=market,
        area=area,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=history_overrides,
    )

    return {
        "sla_type": "history_median",
        "date_from": date_from,
        "date_to": date_to,
        "sla_milestones": history_results,
        **summary,
    }
