from sqlalchemy import Column, Integer, Float, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import ConfigBase
from app.core.config import settings

_S = settings.UTILITY_SCHEMA


class MilestoneDefinition(ConfigBase):
    """
    Milestone definitions stored in DB.

    Each milestone has one or more columns defined in the milestone_columns table.
    The column_role + logic on each MilestoneColumn drives how the actual value
    is extracted from the staging row.
    """
    __tablename__ = "milestone_definitions"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    expected_days = Column(Integer, nullable=False, default=0)
    back_days = Column(Integer, nullable=True)            # canonical days-before-CX-start (right-to-left view)
    depends_on = Column(String(200), nullable=True)       # JSON: '["3710","1327"]' or single key string
    start_gap_days = Column(Integer, nullable=False, default=1)
    task_owner = Column(String(100), nullable=True)       # e.g. "TMO", "PM", "CM", "SE-CoE", "GC", "PDM", "Proj Ops"
    phase_type = Column(String(100), nullable=True)       # e.g. "Pre-Con Phase", "Scoping Phase", "Material & NTP Phase"
    preceding_milestones = Column(Text, nullable=True)    # JSON array of milestone names this one depends on
    following_milestones = Column(Text, nullable=True)    # JSON array of milestone names that depend on this one
    history_expected_days = Column(Integer, nullable=True)  # computed from historical actual dates
    sla_type = Column(String(20), nullable=False, default="default", server_default="default")  # "default" | "history"
    is_skipped = Column(Boolean, default=False, nullable=False, server_default="false")  # admin-set global skip
    project_type = Column(String(50), nullable=False, default="macro", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MilestoneColumn(ConfigBase):
    """
    Per-column config for each milestone.

    column_role determines how this column is used:
      "date"   — parse as date (actual finish)
      "text"   — text presence check (populated = complete)
      "status" — status column that controls skip/use logic

    logic (JSON, nullable) — role-specific rules:
      For "date":   {"pick": "single"} or {"pick": "max"} when multiple date columns
      For "text":   null (just checks if populated)
      For "status": {"skip": ["N","Not Applicable",""], "use_date": ["A"]}

    sort_order — when a milestone has multiple columns, controls processing order.
    """
    __tablename__ = "milestone_columns"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), nullable=False)    # FK to milestone_definitions.key
    column_name = Column(String(200), nullable=False)     # actual staging table column name
    column_role = Column(String(20), nullable=False)      # "date", "text", "status"
    logic = Column(String(500), nullable=True)            # JSON — role-specific rules
    sort_order = Column(Integer, nullable=False, default=0)
    project_type = Column(String(50), nullable=False, default="macro", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PrereqTail(ConfigBase):
    """Prereq tail milestones with offset days."""
    __tablename__ = "prereq_tails"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), nullable=False, unique=True)
    offset_days = Column(Integer, nullable=False, default=0)
    project_type = Column(String(50), nullable=False, default="macro", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GanttConfig(ConfigBase):
    """Key-value config for gantt settings (e.g. CX_START_OFFSET_DAYS)."""
    __tablename__ = "gantt_config"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    project_type = Column(String(50), nullable=False, default="macro", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PrerequisiteTemplate(ConfigBase):
    """Default milestone templates with expected durations."""
    __tablename__ = "prerequisite_templates"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    expected_days = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    path = Column(String(50), nullable=False, default="main")
    depends_on = Column(String(50), nullable=True)
    dependency_type = Column(String(20), nullable=False, default="finish_to_start")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SitePrerequisiteOverride(ConfigBase):
    """Per-site overrides for manual mode."""
    __tablename__ = "site_prerequisite_overrides"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String(50), nullable=False)
    milestone_key = Column(String(50), nullable=False)
    manual_start_date = Column(DateTime, nullable=True)
    manual_end_date = Column(DateTime, nullable=True)
    manual_duration_days = Column(Integer, nullable=True)
    is_manual_mode = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ConstraintThreshold(ConfigBase):
    """
    Configurable thresholds that drive status classification.

    constraint_type splits the rows into two groups:

      "milestone"  — site-level status derived from pending milestone count.
      "overall"    — dashboard-level status derived from on-track site percentage.

    For "milestone": min_pct/max_pct = pending milestone count range.
    For "overall": min_pct/max_pct = percentage range (0–100).

    status_label is the string returned in the API response.
    max_pct=null means no upper bound.
    """
    __tablename__ = "constraint_thresholds"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    constraint_type = Column(String(20), nullable=False, default="milestone")  # "milestone" | "overall"
    name = Column(String(100), nullable=False)
    status_label = Column(String(50), nullable=False, default="")
    color = Column(String(20), nullable=False)
    min_pct = Column(Float, nullable=False, default=0)    # lower bound (inclusive)
    max_pct = Column(Float, nullable=True)                # upper bound (inclusive), null = unbounded
    sort_order = Column(Integer, nullable=False, default=0)
    project_type = Column(String(50), nullable=False, default="macro", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VendorCapacity(ConfigBase):
    """Vendor capacity tracking."""
    __tablename__ = "vendor_capacity"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(200), nullable=False)
    max_daily_sites = Column(Integer, nullable=False, default=5)
    max_concurrent_sites = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserFilter(ConfigBase):
    """
    Persisted per-user filter preferences.

    Each column (region, market, vendor, site_id, area) is stored separately
    so filters are column-wise.  One row per user — upserted on every save.

    Gate checks (saved per-user, applied on every gantt/dashboard query):
      plan_type_include          — JSON array of por_plan_type values to include (IN)
      regional_dev_initiatives   — free-text ILIKE pattern
    """
    __tablename__ = "user_filters"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), unique=True, nullable=False)
    region = Column(String(200), nullable=True)
    market = Column(String(200), nullable=True)
    vendor = Column(String(200), nullable=True)
    site_id = Column(String(200), nullable=True)
    area = Column(String(200), nullable=True)
    plan_type_include = Column(Text, nullable=True)               # JSON array string
    regional_dev_initiatives = Column(String(500), nullable=True) # free-text ILIKE value
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserSkippedPrerequisite(ConfigBase):
    """
    Per-user skipped prerequisites.

    When a user skips a prerequisite (by milestone_key), the planned-date
    calculation treats that milestone as instantly complete (zero duration)
    and recalculates all downstream milestones accordingly.
    """
    __tablename__ = "user_skipped_prerequisites"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False)
    milestone_key = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class UserExpectedDays(ConfigBase):
    """
    Per-user SLA overrides for milestone expected_days.

    When a user sets a custom expected_days for a milestone, planned-date
    calculations use this value instead of the global MilestoneDefinition.expected_days.
    """
    __tablename__ = "user_expected_days"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    milestone_key = Column(String(50), nullable=False)
    expected_days = Column(Integer, nullable=True)
    back_days = Column(Integer, nullable=True)            # per-user override for actual-view back_days
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserHistoryExpectedDays(ConfigBase):
    """
    Per-user history-based SLA days for each milestone.

    When history SLA is computed for a user (from a date range), the computed
    history_expected_days are stored here per-user instead of globally in
    MilestoneDefinition. Each user gets their own set of history-based values.
    """
    __tablename__ = "user_history_expected_days"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    milestone_key = Column(String(50), nullable=False)
    milestone_name = Column(String(200), nullable=True)
    history_expected_days = Column(Integer, nullable=False)
    back_days = Column(Integer, nullable=True)    # right-to-left: median(cx_actual - ms_actual)
    date_from = Column(DateTime, nullable=True)   # date range used for computation
    date_to = Column(DateTime, nullable=True)
    sample_count = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GcCapacityMarketTrial(ConfigBase):
    """
    GC (vendor) capacity per market — predefined read-only table in public schema.

    Records how many sites a vendor can work on in parallel per market.
    Used to flag sites as excluded_due_to_crew_shortage when vendor has more
    assigned sites than their parallel capacity allows.

    NOTE: This table is NOT managed by this app — it is pre-populated externally.
    """
    __tablename__ = "gc_capacity_market_trial"
    __table_args__ = {"schema": "public", "keep_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    gc_company = Column(String(200), nullable=False)
    market = Column(String(200), nullable=False)
    day_wise_gc_capacity = Column(Integer, nullable=False, default=10)


class PaceConstraint(ConfigBase):
    """
    Per-user pace constraints — how many sites can START within a date range
    for a given market/area/region scope.

    Each user manages their own pace constraints. When the gantt chart is
    generated with consider_pace_constraints=True, only that user's
    constraints are applied.
    """
    __tablename__ = "pace_constraints"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    market = Column(String(200), nullable=True)
    area = Column(String(200), nullable=True)
    region = Column(String(200), nullable=True)
    max_sites = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MacroUploadedData(ConfigBase):
    """
    Uploaded planned CX start dates for Macro sites.

    Stores data from CSV/Excel uploads: site_id, region, market,
    project_id, and pj_p_4225_construction_start_finish.
    """
    __tablename__ = "macro_uploaded_data"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String(100), nullable=False, index=True)
    region = Column(String(200), nullable=True)
    market = Column(String(200), nullable=True)
    project_id = Column(String(200), nullable=True)
    pj_p_4225_construction_start_finish = Column(DateTime, nullable=True)
    uploaded_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MacroMilestoneUploadedData(ConfigBase):
    """
    Uploaded per-milestone actual dates for Macro sites.

    Each row = one (user_id, site_id, project_id) triple. The dynamic
    `milestone_actuals` JSON payload stores one entry per provided milestone:
        {
          "3710":  "2026-01-06",         # date-typed milestone
          "cpo":   "SO-12345",           # text milestone
          "steel": {"date": "2026-02-19", "status": "A"},  # with_status milestone
          ...
        }

    Storing the payload as JSON (rather than one column per milestone) lets
    admins add or rename prerequisites without a schema migration.
    """
    __tablename__ = "macro_milestone_uploaded_data"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    project_id = Column(String(200), nullable=True)
    region = Column(String(200), nullable=True)
    market = Column(String(200), nullable=True)
    milestone_actuals = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatHistory(ConfigBase):
    """
    Per-user, per-thread chat history for the AI assistant.

    Stores each message (user or assistant) so the conversation context
    can be loaded from DB instead of being sent from the frontend.
    Each thread_id represents a separate conversation thread.
    """
    __tablename__ = "chat_history"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    thread_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)       # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
