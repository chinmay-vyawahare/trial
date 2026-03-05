from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import config_engine, ConfigBase
from app.models.prerequisite import (
    PrerequisiteTemplate, SitePrerequisiteOverride,
    ConstraintThreshold, VendorCapacity,
    UserFilter, ChatHistory,
)
from app.routers import sites, filters, gate_checks
from app.routers import prerequisites, constraints, admin
from app.routers import assistant, user_filters
from app.init_milestone_data import init_milestone_data

# Create tables for config data on schedular_agent DB
ConfigBase.metadata.create_all(bind=config_engine, tables=[
    PrerequisiteTemplate.__table__,
    SitePrerequisiteOverride.__table__,
    ConstraintThreshold.__table__,
    VendorCapacity.__table__,
    UserFilter.__table__,
    ChatHistory.__table__,
])

# Create milestone/config tables and seed default data if not present
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
app.include_router(filters.router)
app.include_router(prerequisites.router)
app.include_router(constraints.router)
app.include_router(gate_checks.router)
app.include_router(assistant.router)
app.include_router(user_filters.router)
app.include_router(admin.router)

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nokia-schedular-api"}
