from pydantic import BaseModel
from typing import Optional
from datetime import date


class MilestoneData(BaseModel):
    key: str
    name: str
    sort_order: int
    path: str
    expected_days: int
    depends_on: Optional[str] = None
    dependency_type: str = "finish_to_start"
    planned_start: Optional[str] = None
    planned_finish: Optional[str] = None
    actual_finish: Optional[str] = None
    actual_value: Optional[str] = None
    days_since: Optional[int] = None
    days_remaining: Optional[int] = None
    delay_days: Optional[int] = None
    status: str = "NOT STARTED"
    status_color: str = "gray"


class SiteGanttData(BaseModel):
    site_id: str
    project_id: str
    project_name: str
    market: str
    region: Optional[str] = ""
    construction_start_4225: Optional[str] = None
    gc_assignment: Optional[str] = None
    milestones: list[MilestoneData]
    overall_status: str = "PENDING"
    overall_progress: float = 0.0
    critical_path_delay: int = 0


class DashboardSummary(BaseModel):
    total_sites: int
    completed_sites: int
    in_progress_sites: int
    pending_sites: int
    delayed_sites: int
    critical_sites: int
    on_track_sites: int
    markets: list[dict]
    vendor_summary: list[dict]


class PrerequisiteTemplateSchema(BaseModel):
    id: Optional[int] = None
    milestone_key: str
    name: str
    expected_days: int
    sort_order: int
    path: str
    depends_on: Optional[str] = None
    dependency_type: str = "finish_to_start"
    is_active: bool = True

    class Config:
        from_attributes = True


class PrerequisiteTemplateUpdate(BaseModel):
    name: Optional[str] = None
    expected_days: Optional[int] = None
    sort_order: Optional[int] = None
    path: Optional[str] = None
    depends_on: Optional[str] = None
    dependency_type: Optional[str] = None
    is_active: Optional[bool] = None


class SiteOverrideSchema(BaseModel):
    site_id: str
    milestone_key: str
    manual_start_date: Optional[str] = None
    manual_end_date: Optional[str] = None
    manual_duration_days: Optional[int] = None
    is_manual_mode: bool = False


class ConstraintThresholdSchema(BaseModel):
    id: Optional[int] = None
    name: str
    color: str
    min_days: int
    max_days: Optional[int] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class VendorCapacitySchema(BaseModel):
    id: Optional[int] = None
    vendor_name: str
    max_daily_sites: int = 5
    max_concurrent_sites: int = 50
    active_sites: int = 0
    utilization_pct: float = 0.0

    class Config:
        from_attributes = True


class VendorCapacityUpdate(BaseModel):
    max_daily_sites: Optional[int] = None
    max_concurrent_sites: Optional[int] = None
