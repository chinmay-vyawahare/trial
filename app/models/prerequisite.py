from sqlalchemy import Column, Integer, Float, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import ConfigBase


class MilestoneDefinition(ConfigBase):
    """
    Milestone definitions stored in DB.

    Each milestone has one or more columns defined in the milestone_columns table.
    The column_role + logic on each MilestoneColumn drives how the actual value
    is extracted from the staging row.
    """
    __tablename__ = "milestone_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    expected_days = Column(Integer, nullable=False, default=0)
    depends_on = Column(String(200), nullable=True)       # JSON: '["3710","1327"]' or single key string
    start_gap_days = Column(Integer, nullable=False, default=1)
    task_owner = Column(String(100), nullable=True)       # e.g. "TMO", "PM", "CM", "SE-CoE", "GC", "PDM", "Proj Ops"
    phase_type = Column(String(100), nullable=True)       # e.g. "Pre-Con Phase", "Scoping Phase", "Material & NTP Phase"
    preceding_milestones = Column(Text, nullable=True)    # JSON array of milestone names this one depends on
    following_milestones = Column(Text, nullable=True)    # JSON array of milestone names that depend on this one
    history_expected_days = Column(Integer, nullable=True)  # computed from historical actual dates
    sla_type = Column(String(20), nullable=False, default="default", server_default="default")  # "default" | "history"
    is_skipped = Column(Boolean, default=False, nullable=False, server_default="false")  # admin-set global skip
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), nullable=False)    # FK to milestone_definitions.key
    column_name = Column(String(200), nullable=False)     # actual staging table column name
    column_role = Column(String(20), nullable=False)      # "date", "text", "status"
    logic = Column(String(500), nullable=True)            # JSON — role-specific rules
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PrereqTail(ConfigBase):
    """Prereq tail milestones with offset days."""
    __tablename__ = "prereq_tails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), nullable=False, unique=True)
    offset_days = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GanttConfig(ConfigBase):
    """Key-value config for gantt settings (e.g. CX_START_OFFSET_DAYS)."""
    __tablename__ = "gantt_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PrerequisiteTemplate(ConfigBase):
    """Default milestone templates with expected durations."""
    __tablename__ = "prerequisite_templates"

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
    Configurable percentage-based thresholds that drive status classification.

    constraint_type splits the rows into two groups:

      "milestone"  — site-level status derived from milestone percentages.
        Out of all milestones on a site, compute % On Track, % In Progress,
        % Delayed and match against these percentage ranges.
          e.g. min_pct=60, max_pct=100 for "on_track_pct" → ON TRACK
               min_pct=30, max_pct=59  for "on_track_pct" → IN PROGRESS
               min_pct=0,  max_pct=29  for "on_track_pct" → CRITICAL

      "overall"    — dashboard-level status derived from site percentages.
        Out of all sites, compute % ON TRACK, % IN PROGRESS, % CRITICAL
        and match against these percentage ranges.

    status_label is the string returned in the API response
    (e.g. "ON TRACK", "IN PROGRESS", "CRITICAL").

    min_pct / max_pct define the percentage range (0–100).
    max_pct=null means no upper bound (100%).
    """
    __tablename__ = "constraint_thresholds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    constraint_type = Column(String(20), nullable=False, default="milestone")  # "milestone" | "overall"
    name = Column(String(100), nullable=False)
    status_label = Column(String(50), nullable=False, default="")
    color = Column(String(20), nullable=False)
    min_pct = Column(Float, nullable=False, default=0)       # percentage lower bound (inclusive)
    max_pct = Column(Float, nullable=True)                    # percentage upper bound (inclusive), null = 100
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VendorCapacity(ConfigBase):
    """Vendor capacity tracking."""
    __tablename__ = "vendor_capacity"

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
      plan_type_include          — JSON array of por_plan_type values to include (IN),
                                   e.g. '["New Build","FOA"]'
      regional_dev_initiatives   — free-text ILIKE pattern for
                                   por_regional_dev_initiatives,
                                   e.g. '2026 Build Plan'
    """
    __tablename__ = "user_filters"

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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    milestone_key = Column(String(50), nullable=False)
    expected_days = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatHistory(ConfigBase):
    """
    Per-user chat history for the AI assistant.

    Stores each message (user or assistant) so the conversation context
    can be loaded from DB instead of being sent from the frontend.
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)       # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
