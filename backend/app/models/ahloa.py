from sqlalchemy import Column, Integer, Float, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import ConfigBase
from app.core.config import settings

_S = settings.UTILITY_SCHEMA


class AhloaMilestoneDefinition(ConfigBase):
    """
    AHLOA milestone definitions stored in DB.

    Each milestone has one or more columns defined in the ahloa_milestone_columns table.
    The column_role + logic on each AhloaMilestoneColumn drives how the actual value
    is extracted from the staging row.
    """
    __tablename__ = "ahloa_milestone_definitions"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    expected_days = Column(Integer, nullable=False, default=0)
    depends_on = Column(String(200), nullable=True)       # JSON: '["3710","1327"]' or single key string
    start_gap_days = Column(Integer, nullable=False, default=1)
    task_owner = Column(String(100), nullable=True)       # e.g. "TMO", "PM", "CM", "SE-CoE", "GC", "PDM", "Proj Ops"
    phase_type = Column(String(100), nullable=True)       # e.g. "Pre-CX Phase", "Material Phase", "NTP Phase"
    preceding_milestones = Column(Text, nullable=True)    # JSON array of milestone names this one depends on
    following_milestones = Column(Text, nullable=True)    # JSON array of milestone names that depend on this one
    history_expected_days = Column(Integer, nullable=True)  # computed from historical actual dates
    sla_type = Column(String(20), nullable=False, default="default", server_default="default")  # "default" | "history"
    is_skipped = Column(Boolean, default=False, nullable=False, server_default="false")  # admin-set global skip
    project_type = Column(String(50), nullable=False, default="ahloa", server_default="ahloa")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AhloaMilestoneColumn(ConfigBase):
    """
    Per-column config for each AHLOA milestone.

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
    __tablename__ = "ahloa_milestone_columns"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    milestone_key = Column(String(50), nullable=False)    # FK to ahloa_milestone_definitions.key
    column_name = Column(String(200), nullable=False)     # actual staging table column name
    column_role = Column(String(20), nullable=False)      # "date", "text", "status"
    logic = Column(String(500), nullable=True)            # JSON — role-specific rules
    sort_order = Column(Integer, nullable=False, default=0)
    project_type = Column(String(50), nullable=False, default="ahloa", server_default="ahloa")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AhloaConstraintThreshold(ConfigBase):
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
    __tablename__ = "ahloa_constraint_thresholds"
    __table_args__ = {"schema": _S}

    id = Column(Integer, primary_key=True, autoincrement=True)
    constraint_type = Column(String(20), nullable=False, default="milestone")  # "milestone" | "overall"
    name = Column(String(100), nullable=False)
    status_label = Column(String(50), nullable=False, default="")
    color = Column(String(20), nullable=False)
    min_pct = Column(Float, nullable=False, default=0)    # lower bound (inclusive)
    max_pct = Column(Float, nullable=True)                # upper bound (inclusive), null = unbounded
    sort_order = Column(Integer, nullable=False, default=0)
    project_type = Column(String(50), nullable=False, default="ahloa", server_default="macro")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AhloaUserSkippedPrerequisite(ConfigBase):
    """Per-user, per-geo skipped prerequisite for AHLOA.

    At most ONE of (market, area) may be set:
      - market=X, area=NULL  → skip applies to that one market
      - area=X,   market=NULL → skip applies to every market under that area
      - both NULL            → skip applies to all markets for that user
    Both set is rejected by the API as a single-geo-level validation error.
    """
    __tablename__ = "ahloa_user_skipped_prerequisites"
    __table_args__ = (
        UniqueConstraint("user_id", "milestone_key", "market", "area", name="uq_ahloa_skip_user_ms_geo"),
        {"schema": _S},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    milestone_key = Column(String(50), nullable=False)
    market = Column(String(200), nullable=True)
    area = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class AhloaUserExpectedDays(ConfigBase):
    """Per-user SLA overrides for AHLOA milestone expected_days."""
    __tablename__ = "ahloa_user_expected_days"
    __table_args__ = (
        UniqueConstraint("user_id", "milestone_key", name="uq_ahloa_ued_user_ms"),
        {"schema": _S},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    milestone_key = Column(String(50), nullable=False)
    expected_days = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())



