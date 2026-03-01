from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.models.prerequisite import PrerequisiteTemplate, SitePrerequisiteOverride, ConstraintThreshold, VendorCapacity
from app.routers import sites, filters

# Create tables for config data (not the staging table which already exists)
Base.metadata.create_all(bind=engine, tables=[
    PrerequisiteTemplate.__table__,
    SitePrerequisiteOverride.__table__,
    ConstraintThreshold.__table__,
    VendorCapacity.__table__,
])

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


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "nokia-schedular-api"}
