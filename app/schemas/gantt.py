import json
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date


class MilestoneData(BaseModel):
    key: str
    name: str
    sort_order: int
    path: str
    expected_days: int
    dependency_type: str = "finish_to_start"
    task_owner: Optional[str] = None
    phase_type: Optional[str] = None
    preceding_milestones: Optional[list[str]] = None    # milestones this one depends on (before)
    following_milestones: Optional[list[str]] = None     # milestones that depend on this one (after)
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
    dashboard_status: str
    on_track_pct: float
    total_sites: int
    in_progress_sites: int
    critical_sites: int
    on_track_sites: int


class PrerequisiteTemplateSchema(BaseModel):
    """Output schema — id is auto-generated."""
    model_config = {"from_attributes": True}

    id: int
    milestone_key: str
    name: str
    expected_days: int
    sort_order: int
    path: str
    depends_on: Optional[str] = None
    dependency_type: str = "finish_to_start"
    is_active: bool = True


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
    """Output schema — always includes the auto-generated id."""
    model_config = {"from_attributes": True}

    id: int
    constraint_type: str = "milestone"
    name: str
    status_label: str
    color: str
    min_pct: float = 0
    max_pct: Optional[float] = None
    sort_order: int = 0


class ConstraintThresholdCreate(BaseModel):
    """Input schema for POST — id is auto-generated, never sent by the client."""
    constraint_type: str = "milestone"  # "milestone" | "overall"
    name: str
    status_label: str
    color: str
    min_pct: float = 0          # percentage lower bound (inclusive)
    max_pct: Optional[float] = None  # percentage upper bound (inclusive), null = 100
    sort_order: int = 0


class ConstraintThresholdUpdate(BaseModel):
    name: Optional[str] = None
    status_label: Optional[str] = None
    color: Optional[str] = None
    min_pct: Optional[float] = None
    max_pct: Optional[float] = None
    sort_order: Optional[int] = None


class VendorCapacitySchema(BaseModel):
    """Output schema — id is auto-generated."""
    model_config = {"from_attributes": True}

    id: int
    vendor_name: str
    max_daily_sites: int = 5
    max_concurrent_sites: int = 50
    active_sites: int = 0
    utilization_pct: float = 0.0


class VendorCapacityUpdate(BaseModel):
    max_daily_sites: Optional[int] = None
    max_concurrent_sites: Optional[int] = None


# ----------------------------------------------------------------
# Milestone Definition CRUD schemas
# ----------------------------------------------------------------

class MilestoneDefinitionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    key: str
    name: str
    sort_order: int
    expected_days: int
    start_gap_days: int = 1
    task_owner: Optional[str] = None
    phase_type: Optional[str] = None
    preceding_milestones: Optional[list[str]] = None    # milestones this one depends on (before)
    following_milestones: Optional[list[str]] = None     # milestones that depend on this one (after)

    @field_validator("preceding_milestones", "following_milestones", mode="before")
    @classmethod
    def parse_json_string(cls, v):
        """DB stores these as JSON strings — parse to list if needed."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v


class MilestoneDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    expected_days: Optional[int] = None
    start_gap_days: Optional[int] = None
    task_owner: Optional[str] = None
    phase_type: Optional[str] = None


class MilestoneColumnCreate(BaseModel):
    """Column definition for a new prerequisite."""
    column_name: str                             # staging table column name
    column_role: str = "date"                    # "date", "text", "status"
    logic: Optional[str] = None                  # JSON string: {"pick":"min"}, {"skip":[...],"use_date":[...]}


class MilestoneDefinitionCreate(BaseModel):
    """
    Input schema for creating a new prerequisite.

    preceding_milestone_keys: list of milestone keys that this new prerequisite depends on.
                              These become the depends_on value.
                              e.g. ["1310"] or ["3710", "1327"] for multi-dependency.
    following_milestone_keys: list of milestone keys that should depend on this new prerequisite.
                              Those milestones will have their depends_on rewired from their
                              current dependency to the new milestone's key.
    insert_after_key:         the milestone key after which to insert (for sort_order).
                              If null, inferred from preceding_milestone_keys or appended at end.
    columns:                  list of column definitions for the staging table.
    """
    key: str
    name: str
    expected_days: int = 0
    start_gap_days: int = 1
    task_owner: Optional[str] = None
    phase_type: Optional[str] = None
    preceding_milestone_keys: Optional[list[str]] = None   # keys this milestone depends on
    following_milestone_keys: Optional[list[str]] = None    # keys that should depend on this milestone
    insert_after_key: Optional[str] = None                  # for sort_order positioning (None = auto)
    columns: list[MilestoneColumnCreate] = []               # staging table column mappings


class MilestoneDefinitionCreateOut(BaseModel):
    """Output schema after creating a new prerequisite — includes computed dependency info."""
    model_config = {"from_attributes": True}

    id: int
    key: str
    name: str
    sort_order: int
    expected_days: int
    start_gap_days: int = 1
    task_owner: Optional[str] = None
    phase_type: Optional[str] = None
    depends_on: Optional[str] = None
    preceding_milestones: Optional[list[str]] = None
    following_milestones: Optional[list[str]] = None
    columns: list[dict] = []

    @field_validator("preceding_milestones", "following_milestones", mode="before")
    @classmethod
    def parse_json_string_create(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v


class MilestoneReorderItem(BaseModel):
    key: str
    sort_order: int


class MilestoneReorderRequest(BaseModel):
    """Accepts a list of {key, sort_order} to reorder all milestones at once."""
    items: list[MilestoneReorderItem]


# ----------------------------------------------------------------
# User Filter schemas
# ----------------------------------------------------------------

class UserFilterSave(BaseModel):
    user_id: str
    region: Optional[str] = None
    market: Optional[str] = None
    vendor: Optional[str] = None
    site_id: Optional[str] = None
    area: Optional[str] = None
    plan_type_include: Optional[list[str]] = None           # e.g. ["New Build", "FOA"]
    regional_dev_initiatives: Optional[str] = None          # free-text ILIKE, e.g. "2026 Build Plan"


class UserFilterOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: str
    region: Optional[str] = None
    market: Optional[str] = None
    vendor: Optional[str] = None
    site_id: Optional[str] = None
    area: Optional[str] = None
    plan_type_include: Optional[str] = None                 # stored as JSON string in DB
    regional_dev_initiatives: Optional[str] = None


# ----------------------------------------------------------------
# User Skipped Prerequisite schemas
# ----------------------------------------------------------------

class SkipPrerequisiteRequest(BaseModel):
    milestone_key: str


class SkipPrerequisiteOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    key: str
    name: str
    is_skipped: bool
