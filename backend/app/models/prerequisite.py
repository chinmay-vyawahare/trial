from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class PrerequisiteTemplate(Base):
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


class SitePrerequisiteOverride(Base):
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


class ConstraintThreshold(Base):
    """Configurable delay thresholds."""
    __tablename__ = "constraint_thresholds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    color = Column(String(20), nullable=False)
    min_days = Column(Integer, nullable=False)
    max_days = Column(Integer, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class VendorCapacity(Base):
    """Vendor capacity tracking."""
    __tablename__ = "vendor_capacity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(200), nullable=False)
    max_daily_sites = Column(Integer, nullable=False, default=5)
    max_concurrent_sites = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
