import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sa_text, inspect
from app.core.database import engine, config_engine, ConfigBase, STAGING_TABLE
from app.core.config import settings
from app.models.prerequisite import (
    PrerequisiteTemplate, SitePrerequisiteOverride,
    ConstraintThreshold, VendorCapacity,
    UserFilter, ChatHistory, UserExpectedDays,
    PaceConstraint,
)
from app.routers import sites, filters, gate_checks
from app.routers import prerequisites, constraints, admin
from app.routers import assistant, user_filters, sla_history
from app.routers import user_expected_days
from app.routers import export, dashboard
from app.routers import gc_capacity, pace_constraints, calendar
from app.routers import analytics
from app.init_milestone_data import init_milestone_data
from app.services.assistant.nodes.simulation import set_main_loop

logger = logging.getLogger(__name__)

ConfigBase.metadata.create_all(bind=config_engine, tables=[
    PrerequisiteTemplate.__table__,
    SitePrerequisiteOverride.__table__,
    ConstraintThreshold.__table__,
    VendorCapacity.__table__,
    UserFilter.__table__,
    ChatHistory.__table__,
    UserExpectedDays.__table__,
    PaceConstraint.__table__,
])

init_milestone_data()

app = FastAPI(title="Nokia Schedular App", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(dashboard.router)
app.include_router(calendar.router)
app.include_router(sla_history.router)
app.include_router(user_expected_days.router)
app.include_router(filters.router)
app.include_router(prerequisites.router)
app.include_router(constraints.router)
app.include_router(gate_checks.router)
app.include_router(assistant.router)
app.include_router(user_filters.router)
app.include_router(admin.router)
app.include_router(export.router)
app.include_router(gc_capacity.router)
app.include_router(pace_constraints.router)
app.include_router(analytics.router)

@app.on_event("startup")
async def _capture_event_loop():
    """Capture FastAPI's event loop so simulation background tasks survive."""
    import asyncio
    set_main_loop(asyncio.get_running_loop())


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a clean 500 response."""
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nokia-schedular-api"}
