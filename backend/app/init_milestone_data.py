"""
Seed milestone definitions, milestone columns, prereq tails, and gantt config
into the database.

On app startup this module:
  1. Creates the tables if they don't already exist.
  2. Checks whether the tables already contain data.
  3. If empty, inserts the default seed rows.
  4. If data already exists, does nothing (no overwrite).

This is the SINGLE source of truth for default milestone config.
"""

import json
import logging
from sqlalchemy.orm import Session
from app.core.database import config_engine, ConfigBase, ConfigSessionLocal
from app.models.prerequisite import (
    MacroUploadedData, MilestoneDefinition, MilestoneColumn, PrereqTail, GanttConfig,
    ConstraintThreshold, UserHistoryExpectedDays,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Seed data — Milestone Definitions
# ----------------------------------------------------------------
SEED_MILESTONES = [
    {
        "key": "3710",
        "name": "Entitlement Complete (MS 3710)",
        "sort_order": 1,
        "expected_days": 0,
        "depends_on": None,
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps([]),
        "following_milestones": json.dumps(["Pre-NTP Document Received", "BOM in BAT (MS 3850)"]),
    },
    {
        "key": "1310",
        "name": "Pre-NTP Document Received",
        "sort_order": 2,
        "expected_days": 2,
        "depends_on": "3710",
        "start_gap_days": 0,
        "task_owner": "Proj Ops",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Entitlement Complete (MS 3710)"]),
        "following_milestones": json.dumps(["Site Walk Performed"]),
    },
    {
        "key": "site_walk",
        "name": "Site Walk Performed",
        "sort_order": 3,
        "expected_days": 7,
        "depends_on": "1310",
        "start_gap_days": 1,
        "task_owner": "CM",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Pre-NTP Document Received"]),
        "following_milestones": json.dumps(["Ready for Scoping (MS 1323)"]),
    },
    {
        "key": "1323",
        "name": "Ready for Scoping (MS 1323)",
        "sort_order": 4,
        "expected_days": 3,
        "depends_on": "site_walk",
        "start_gap_days": 1,
        "task_owner": "SE-CoE",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Site Walk Performed"]),
        "following_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
    },
    {
        "key": "1327",
        "name": "Scoping Validated by GC (MS 1327)",
        "sort_order": 5,
        "expected_days": 7,
        "depends_on": "1323",
        "start_gap_days": 1,
        "task_owner": "SE-CoE",
        "phase_type": "Scoping Phase",
        "preceding_milestones": json.dumps(["Ready for Scoping (MS 1323)"]),
        "following_milestones": json.dumps([
            "BOM in BAT (MS 3850)",
            "Quote Submitted to Customer",
            "Steel Received (If applicable)",
            "NTP Received",
            "Access Confirmation",
        ]),
    },
    {
        "key": "3850",
        "name": "BOM in BAT (MS 3850)",
        "sort_order": 6,
        "expected_days": 0,      # duration derived at runtime: max(expected_days of predecessors)
        "depends_on": json.dumps(["3710", "1327"]),
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Scoping Phase",
        "preceding_milestones": json.dumps(["Entitlement Complete (MS 3710)", "Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps(["BOM Received in AIMS (MS 3875)"]),
    },
    {
        "key": "quote",
        "name": "Quote Submitted to Customer",
        "sort_order": 7,
        "expected_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "PM",
        "phase_type": "Scoping Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps(["CPO Available"]),
    },
    {
        "key": "3875",
        "name": "BOM Received in AIMS (MS 3875)",
        "sort_order": 8,
        "expected_days": 21,
        "depends_on": "3850",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["BOM in BAT (MS 3850)"]),
        "following_milestones": json.dumps([]),
    },
    {
        "key": "cpo",
        "name": "CPO Available",
        "sort_order": 9,
        "expected_days": 14,
        "depends_on": "quote",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Quote Submitted to Customer"]),
        "following_milestones": json.dumps(["SPO Issued"]),
    },
    {
        "key": "1555",
        "name": "SPO Issued",
        "sort_order": 10,
        "expected_days": 5,
        "depends_on": "cpo",
        "start_gap_days": 1,
        "task_owner": "PDM",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["CPO Available"]),
        "following_milestones": json.dumps([]),
    },
    {
        "key": "steel",
        "name": "Steel Received (If applicable)",
        "sort_order": 11,
        "expected_days": 14,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "GC",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps(["Material Pickup by GC (MS 3925)"]),
    },
    {
        "key": "3925",
        "name": "Material Pickup by GC (MS 3925)",
        "sort_order": 12,
        "expected_days": 5,
        "depends_on": "steel",
        "start_gap_days": 1,
        "task_owner": "GC",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Steel Received (If applicable)"]),
        "following_milestones": json.dumps([]),
    },
    {
        "key": "1407",
        "name": "NTP Received",
        "sort_order": 13,
        "expected_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps([]),
    },
    {
        "key": "4000",
        "name": "Access Confirmation",
        "sort_order": 14,
        "expected_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "CM",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps([]),
    },
]

# ----------------------------------------------------------------
# Seed data — Milestone Columns
#
# column_role: "date", "text", "status"
# logic (JSON):
#   date   → {"pick": "single"} or {"pick": "max"}
#   text   → null
#   status → {"skip": [...], "use_date": [...]}
# ----------------------------------------------------------------
SEED_MILESTONE_COLUMNS = [
    # 3710 — single date
    {"milestone_key": "3710", "column_name": "pj_a_3710_ran_entitlement_complete_finish",
     "column_role": "date", "logic": None, "sort_order": 1},

    # 1310 — single date
    {"milestone_key": "1310", "column_name": "ms_1310_pre_construction_package_received_actual",
     "column_role": "date", "logic": None, "sort_order": 2},

    # site_walk — max (latest) of 2 date columns
    {"milestone_key": "site_walk", "column_name": "ms_1316_pre_con_site_walk_completed_actual",
     "column_role": "date", "logic": json.dumps({"pick": "max"}), "sort_order": 3},
    {"milestone_key": "site_walk", "column_name": "ms_1321_talon_view_drone_svcs_actual",
     "column_role": "date", "logic": json.dumps({"pick": "max"}), "sort_order": 4},

    # 1323 — single date
    {"milestone_key": "1323", "column_name": "ms_1323_ready_for_scoping_actual",
     "column_role": "date", "logic": None, "sort_order": 5},

    # 1327 — single date
    {"milestone_key": "1327", "column_name": "ms_1327_scoping_and_quoting_package_validated_actual",
     "column_role": "date", "logic": None, "sort_order": 6},

    # 3850 — single date
    {"milestone_key": "3850", "column_name": "pj_a_3850_bom_submitted_bom_in_bat_finish",
     "column_role": "date", "logic": None, "sort_order": 7},

    # 3875 — single date
    {"milestone_key": "3875", "column_name": "pj_a_3875_bom_received_bom_in_aims_finish",
     "column_role": "date", "logic": None, "sort_order": 8},

    # steel — date + status
    {"milestone_key": "steel", "column_name": "pj_steel_received_date",
     "column_role": "date", "logic": None, "sort_order": 9},
    {"milestone_key": "steel", "column_name": "pj_steel_received_status",
     "column_role": "status", "logic": json.dumps({"skip": ["N", "Not Applicable", ""], "use_date": ["A"]}), "sort_order": 10},

    # 3925 — single date
    {"milestone_key": "3925", "column_name": "pj_a_3925_msl_pickup_date_finish",
     "column_role": "date", "logic": None, "sort_order": 11},

    # quote — single date
    {"milestone_key": "quote", "column_name": "ms_1331_scoping_package_submitted_actual",
     "column_role": "date", "logic": None, "sort_order": 12},

    # cpo — text presence check
    {"milestone_key": "cpo", "column_name": "ms1555_construction_complete_so_header",
     "column_role": "text", "logic": None, "sort_order": 13},

    # 1555 — single date
    {"milestone_key": "1555", "column_name": "ms1555_construction_complete_spo_issued_date",
     "column_role": "date", "logic": None, "sort_order": 14},

    # 4000 — text presence check
    {"milestone_key": "4000", "column_name": "pj_a_4000_ll_ntp_received",
     "column_role": "text", "logic": None, "sort_order": 15},

    # 1407 — single date
    {"milestone_key": "1407", "column_name": "ms_1407_tower_ntp_validated_actual",
     "column_role": "date", "logic": None, "sort_order": 16},
]

SEED_PREREQ_TAILS = [
    {"milestone_key": "3925",  "offset_days": 4},
    {"milestone_key": "steel", "offset_days": 7},
    {"milestone_key": "1555",  "offset_days": 5},
    {"milestone_key": "4000",  "offset_days": 7},
    {"milestone_key": "1407",  "offset_days": 7},
]

SEED_GANTT_CONFIG = [
    {
        "config_key": "CX_START_OFFSET_DAYS",
        "config_value": "4",
        "description": "Days after All Prerequisites Complete to Forecasted CX Start",
    },
    {
        "config_key": "PLANNED_START_COLUMN",
        "config_value": "pj_p_3710_ran_entitlement_complete_finish",
        "description": "Staging table column for the root milestone planned start date",
    },
]

# ----------------------------------------------------------------
# Seed data — Constraint Thresholds (percentage-based)
#
# constraint_type: "milestone" | "overall"
#
# "milestone" rows — site-level status based on % of on-track milestones.
#   Out of all milestones on a site, compute the on_track percentage.
#   Checked in sort_order; first matching range wins.
#
# "overall" rows — dashboard-level status based on % of on-track sites.
#   Out of all sites, compute the on_track_sites percentage.
#   Checked in sort_order; first matching range wins.
#
# min_pct / max_pct define percentage ranges (0-100).
# For "milestone": on-track milestone percentage. For "overall": on-track site percentage.
# max_pct = None means no upper bound.
# ----------------------------------------------------------------
SEED_CONSTRAINT_THRESHOLDS = [
    # --- milestone-level: site overall status from on-track milestone percentage ---
    {
        "constraint_type": "milestone",
        "name": "On Track",
        "status_label": "ON TRACK",
        "color": "green",
        "min_pct": 60,
        "max_pct": None,     # 60%+ on-track milestones
        "sort_order": 1,
    },
    {
        "constraint_type": "milestone",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 59.99,    # 30–59.99% on-track milestones
        "sort_order": 2,
    },
    {
        "constraint_type": "milestone",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track milestones
        "sort_order": 3,
    },
    # --- overall: dashboard status from on-track site percentage ---
    {
        "constraint_type": "overall",
        "name": "On Track",
        "status_label": "ON TRACK",
        "color": "green",
        "min_pct": 60,
        "max_pct": None,     # 60%+ on-track sites
        "sort_order": 1,
    },
    {
        "constraint_type": "overall",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 59.99,    # 30–59.99% on-track sites
        "sort_order": 2,
    },
    {
        "constraint_type": "overall",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track sites
        "sort_order": 3,
    },
]

def init_milestone_data():
    """Create tables and seed default data if not already present."""
    ConfigBase.metadata.create_all(bind=config_engine, tables=[
        MilestoneDefinition.__table__,
        MilestoneColumn.__table__,
        PrereqTail.__table__,
        GanttConfig.__table__,
        ConstraintThreshold.__table__,
        UserHistoryExpectedDays.__table__,
        MacroUploadedData.__table__,
    ])

    db: Session = ConfigSessionLocal()
    try:
        if db.query(MilestoneDefinition).count() == 0:
            for ms_data in SEED_MILESTONES:
                db.add(MilestoneDefinition(**ms_data))
            db.commit()
            logger.info("Seeded %d milestone definitions.", len(SEED_MILESTONES))

        if db.query(MilestoneColumn).count() == 0:
            for col_data in SEED_MILESTONE_COLUMNS:
                db.add(MilestoneColumn(**col_data))
            db.commit()
            logger.info("Seeded %d milestone columns.", len(SEED_MILESTONE_COLUMNS))

        if db.query(PrereqTail).count() == 0:
            for tail_data in SEED_PREREQ_TAILS:
                db.add(PrereqTail(**tail_data))
            db.commit()
            logger.info("Seeded %d prereq tails.", len(SEED_PREREQ_TAILS))

        if db.query(GanttConfig).count() == 0:
            for cfg_data in SEED_GANTT_CONFIG:
                db.add(GanttConfig(**cfg_data))
            db.commit()
            logger.info("Seeded %d gantt config entries.", len(SEED_GANTT_CONFIG))

        if db.query(ConstraintThreshold).count() == 0:
            for ct_data in SEED_CONSTRAINT_THRESHOLDS:
                db.add(ConstraintThreshold(**ct_data))
            db.commit()
            logger.info("Seeded %d constraint thresholds.", len(SEED_CONSTRAINT_THRESHOLDS))

    except Exception:
        db.rollback()
        logger.exception("Failed to seed milestone data.")
        raise
    finally:
        db.close()
