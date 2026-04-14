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
from app.models.ahloa import AhloaMilestoneDefinition, AhloaMilestoneColumn, AhloaConstraintThreshold

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
        "back_days": 49,
        "depends_on": None,
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps([]),
        "following_milestones": json.dumps(["Pre-NTP Document Received", "BOM in BAT (MS 3850)"]),
        "project_type": "macro",
    },
    {
        "key": "1310",
        "name": "Pre-NTP Document Received",
        "sort_order": 2,
        "expected_days": 2,
        "back_days": 47,
        "depends_on": "3710",
        "start_gap_days": 0,
        "task_owner": "Proj Ops",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Entitlement Complete (MS 3710)"]),
        "following_milestones": json.dumps(["Site Walk Performed"]),
        "project_type": "macro",
    },
    {
        "key": "site_walk",
        "name": "Site Walk Performed",
        "sort_order": 3,
        "expected_days": 7,
        "back_days": 40,
        "depends_on": "1310",
        "start_gap_days": 1,
        "task_owner": "CM",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Pre-NTP Document Received"]),
        "following_milestones": json.dumps(["Ready for Scoping (MS 1323)"]),
        "project_type": "macro",
    },
    {
        "key": "1323",
        "name": "Ready for Scoping (MS 1323)",
        "sort_order": 4,
        "expected_days": 3,
        "back_days": 37,
        "depends_on": "site_walk",
        "start_gap_days": 1,
        "task_owner": "SE-CoE",
        "phase_type": "Pre-Con Phase",
        "preceding_milestones": json.dumps(["Site Walk Performed"]),
        "following_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "project_type": "macro",
    },
    {
        "key": "1327",
        "name": "Scoping Validated by GC (MS 1327)",
        "sort_order": 5,
        "expected_days": 7,
        "back_days": 30,
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
        "project_type": "macro",
    },
    {
        "key": "3850",
        "name": "BOM in BAT (MS 3850)",
        "sort_order": 6,
        "expected_days": 0,      # duration derived at runtime: max(expected_days of predecessors)
        "back_days": 30,
        "depends_on": json.dumps(["3710", "1327"]),
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Scoping Phase",
        "preceding_milestones": json.dumps(["Entitlement Complete (MS 3710)", "Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps(["BOM Received in AIMS (MS 3875)"]),
        "project_type": "macro",
    },
    {
        "key": "quote",
        "name": "Quote Submitted to Customer",
        "sort_order": 7,
        "expected_days": 7,
        "back_days": 21,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "PM",
        "phase_type": "Scoping Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps(["CPO Available"]),
        "project_type": "macro",
    },
    {
        "key": "3875",
        "name": "BOM Received in AIMS (MS 3875)",
        "sort_order": 8,
        "expected_days": 21,
        "back_days": 9,
        "depends_on": "3850",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["BOM in BAT (MS 3850)"]),
        "following_milestones": json.dumps(["Material Pickup by GC (MS 3925)"]),
        "project_type": "macro",
    },
    {
        "key": "cpo",
        "name": "CPO Available",
        "sort_order": 9,
        "expected_days": 14,
        "back_days": 7,
        "depends_on": "quote",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Quote Submitted to Customer"]),
        "following_milestones": json.dumps(["SPO Issued"]),
        "project_type": "macro",
    },
    {
        "key": "1555",
        "name": "SPO Issued",
        "sort_order": 10,
        "expected_days": 2,
        "back_days": 5,
        "depends_on": "cpo",
        "start_gap_days": 1,
        "task_owner": "PDM",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["CPO Available"]),
        "following_milestones": json.dumps([]),
        "project_type": "macro",
    },
    {
        "key": "steel",
        "name": "Steel Received (If applicable)",
        "sort_order": 11,
        "expected_days": 14,
        "back_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "GC",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps([]),
        "project_type": "macro",
    },
    {
        "key": "3925",
        "name": "Material Pickup by GC (MS 3925)",
        "sort_order": 12,
        "expected_days": 5,
        "back_days": 4,
        "depends_on": "3875",
        "start_gap_days": 1,
        "task_owner": "GC",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["BOM Received in AIMS (MS 3875)"]),
        "following_milestones": json.dumps([]),
        "project_type": "macro",
    },
    {
        "key": "1407",
        "name": "NTP Received",
        "sort_order": 13,
        "expected_days": 7,
        "back_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "TMO",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps([]),
        "project_type": "macro",
    },
    {
        "key": "4000",
        "name": "Access Confirmation",
        "sort_order": 14,
        "expected_days": 7,
        "back_days": 7,
        "depends_on": "1327",
        "start_gap_days": 1,
        "task_owner": "CM",
        "phase_type": "Material & NTP Phase",
        "preceding_milestones": json.dumps(["Scoping Validated by GC (MS 1327)"]),
        "following_milestones": json.dumps([]),
        "project_type": "macro",
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
     "column_role": "date", "logic": None, "sort_order": 1, "project_type": "macro"},

    # 1310 — single date
    {"milestone_key": "1310", "column_name": "ms_1310_pre_construction_package_received_actual",
     "column_role": "date", "logic": None, "sort_order": 2, "project_type": "macro"},

    # site_walk — max (latest) of 2 date columns
    {"milestone_key": "site_walk", "column_name": "ms_1316_pre_con_site_walk_completed_actual",
     "column_role": "date", "logic": json.dumps({"pick": "max"}), "sort_order": 3, "project_type": "macro"},
    {"milestone_key": "site_walk", "column_name": "ms_1321_talon_view_drone_svcs_actual",
     "column_role": "date", "logic": json.dumps({"pick": "max"}), "sort_order": 4, "project_type": "macro"},

    # 1323 — single date
    {"milestone_key": "1323", "column_name": "ms_1323_ready_for_scoping_actual",
     "column_role": "date", "logic": None, "sort_order": 5, "project_type": "macro"},

    # 1327 — single date
    {"milestone_key": "1327", "column_name": "ms_1327_scoping_and_quoting_package_validated_actual",
     "column_role": "date", "logic": None, "sort_order": 6, "project_type": "macro"},

    # 3850 — single date
    {"milestone_key": "3850", "column_name": "pj_a_3850_bom_submitted_bom_in_bat_finish",
     "column_role": "date", "logic": None, "sort_order": 7, "project_type": "macro"},

    # 3875 — single date
    {"milestone_key": "3875", "column_name": "pj_a_3875_bom_received_bom_in_aims_finish",
     "column_role": "date", "logic": None, "sort_order": 8, "project_type": "macro"},

    # steel — date + status
    {"milestone_key": "steel", "column_name": "pj_steel_received_date",
     "column_role": "date", "logic": None, "sort_order": 9, "project_type": "macro"},
    {"milestone_key": "steel", "column_name": "pj_steel_received_status",
     "column_role": "status", "logic": json.dumps({"skip": ["N", "Not Applicable", ""], "use_date": ["A"]}), "sort_order": 10, "project_type": "macro"},

    # 3925 — single date
    {"milestone_key": "3925", "column_name": "pj_a_3925_msl_pickup_date_finish",
     "column_role": "date", "logic": None, "sort_order": 11, "project_type": "macro"},

    # quote — single date
    {"milestone_key": "quote", "column_name": "ms_1331_scoping_package_submitted_actual",
     "column_role": "date", "logic": None, "sort_order": 12, "project_type": "macro"},

    # cpo — text presence check
    {"milestone_key": "cpo", "column_name": "ms1555_construction_complete_so_header",
     "column_role": "text", "logic": None, "sort_order": 13, "project_type": "macro"},

    # 1555 — single date
    {"milestone_key": "1555", "column_name": "ms1555_construction_complete_spo_issued_date",
     "column_role": "date", "logic": None, "sort_order": 14, "project_type": "macro"},

    # 4000 — text presence check
    {"milestone_key": "4000", "column_name": "pj_a_4000_ll_ntp_received",
     "column_role": "text", "logic": None, "sort_order": 15, "project_type": "macro"},

    # 1407 — single date
    {"milestone_key": "1407", "column_name": "ms_1407_tower_ntp_validated_actual",
     "column_role": "date", "logic": None, "sort_order": 16, "project_type": "macro"},
]

SEED_PREREQ_TAILS = [
    {"milestone_key": "3925",  "offset_days": 4, "project_type": "macro"},
    {"milestone_key": "steel", "offset_days": 7, "project_type": "macro"},
    {"milestone_key": "1555",  "offset_days": 5, "project_type": "macro"},
    {"milestone_key": "4000",  "offset_days": 7, "project_type": "macro"},
    {"milestone_key": "1407",  "offset_days": 7, "project_type": "macro"},
]

SEED_GANTT_CONFIG = [
    {
        "config_key": "CX_START_OFFSET_DAYS",
        "config_value": "4",
        "description": "Days after All Prerequisites Complete to Forecasted CX Start",
        "project_type": "macro",
    },
    {
        "config_key": "PLANNED_START_COLUMN",
        "config_value": "pj_p_3710_ran_entitlement_complete_finish",
        "description": "Staging table column for the root milestone planned start date",
        "project_type": "macro",
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
        "min_pct": 65,
        "max_pct": 92.99,     # 60%+ on-track milestones
        "sort_order": 1,
        "project_type": "macro",
    },
    {
        "constraint_type": "milestone",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 64.99,    # 30–59.99% on-track milestones
        "sort_order": 2,
        "project_type": "macro",
    },
    {
        "constraint_type": "milestone",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track milestones
        "sort_order": 3,
        "project_type": "macro",
    },
    {
        "constraint_type": "milestone",
        "name": "ready",
        "status_label": "READY",
        "color": "green",
        "min_pct": 93,
        "max_pct": 100,    # 93–100% ready milestones
        "sort_order": 4,
        "project_type": "macro",
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
        "project_type": "macro",
    },
    {
        "constraint_type": "overall",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 59.99,    # 30–59.99% on-track sites
        "sort_order": 2,
        "project_type": "macro",
    },
    {
        "constraint_type": "overall",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track sites
        "sort_order": 3,
        "project_type": "macro",
    },
]

SEED_AHLOA_CONSTRAINT_THRESHOLDS = [
    # --- milestone-level: site overall status from on-track milestone percentage ---
    {
        "constraint_type": "milestone",
        "name": "On Track",
        "status_label": "ON TRACK",
        "color": "green",
        "min_pct": 65,
        "max_pct": 92.99,     # 60%+ on-track milestones
        "sort_order": 1,
        "project_type": "ahloa",
    },
    {
        "constraint_type": "milestone",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 64.99,    # 30–59.99% on-track milestones
        "sort_order": 2,
        "project_type": "ahloa",
    },
    {
        "constraint_type": "milestone",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track milestones
        "sort_order": 3,
        "project_type": "ahloa",
    },
    {
        "constraint_type": "milestone",
        "name": "ready",
        "status_label": "READY",
        "color": "green",
        "min_pct": 93,
        "max_pct": 100,    # 93–100% ready milestones
        "sort_order": 4,
        "project_type": "ahloa",
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
        "project_type": "ahloa",
    },
    {
        "constraint_type": "overall",
        "name": "In Progress",
        "status_label": "IN PROGRESS",
        "color": "orange",
        "min_pct": 30,
        "max_pct": 59.99,    # 30–59.99% on-track sites
        "sort_order": 2,
        "project_type": "ahloa",
    },
    {
        "constraint_type": "overall",
        "name": "Critical",
        "status_label": "CRITICAL",
        "color": "red",
        "min_pct": 0,
        "max_pct": 29.99,    # 0–29.99% on-track sites
        "sort_order": 3,
        "project_type": "ahloa",
    },
]


# ----------------------------------------------------------------
# Seed data — AHLOA Milestone Definitions
# ----------------------------------------------------------------
SEED_AHLOA_MILESTONES = [
    {
        "key": "cpo",
        "name": "CPO For Site",
        "sort_order": 1,
        "expected_days": 0,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Pre-CX Phase",
        "project_type": "ahloa",
    },
    {
        "key": "3850",
        "name": "BOM Ready (MS 3850)",
        "sort_order": 2,
        "expected_days": 42,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "CM",
        "phase_type": "Material Phase",
        "project_type": "ahloa",
    },
    {
        "key": "3875",
        "name": "BOM Material Available in MSL (MS 3875)",
        "sort_order": 3,
        "expected_days": 10,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Material Phase",
        "project_type": "ahloa",
    },
    {
        "key": "3925",
        "name": "Material Pickup by GC (MS 3925)",
        "sort_order": 4,
        "expected_days": 7,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "Material Phase",
        "project_type": "ahloa",
    },
    {
        "key": "4000",
        "name": "LL NTP Ready (MS 4000)",
        "sort_order": 5,
        "expected_days": 28,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "NTP Phase",
        "project_type": "ahloa",
    },
    {
        "key": "4075",
        "name": "Overall NTP Ready (MS 4075)",
        "sort_order": 6,
        "expected_days": 28,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "NTP Phase",
        "project_type": "ahloa",
    },
    {
        "key": "4100",
        "name": "Final NTP Ready (MS 4100)",
        "sort_order": 7,
        "expected_days": 28,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "PDM",
        "phase_type": "NTP Phase",
        "project_type": "ahloa",
    },
    {
        "key": "spo_gc_cx",
        "name": "SPO to GC for CX",
        "sort_order": 8,
        "expected_days": 42,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "PROJECT-OPS",
        "phase_type": "SPO Phase",
        "project_type": "ahloa",
    },
    {
        "key": "crane",
        "name": "Crane",
        "sort_order": 9,
        "expected_days": 14,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "Crane Readiness Phase",
        "project_type": "ahloa",
    },
    {
        "key": "talon_scoping",
        "name": "Talon Session for Scoping",
        "sort_order": 10,
        "expected_days": 14,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "SE-CoE",
        "phase_type": "Scoping Phase",
        "project_type": "ahloa",
    },
    {
        "key": "talon_scop",
        "name": "Talon Session for SCOP",
        "sort_order": 11,
        "expected_days": 14,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "SE-CoE",
        "phase_type": "SCOP Phase",
        "project_type": "ahloa",
    },
    {
        "key": "nas_upload",
        "name": "Planned Activity Upload Status in NAS",
        "sort_order": 12,
        "expected_days": 7,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "Outage Readiness Phase",
        "project_type": "ahloa",
    },
]

# ----------------------------------------------------------------
# Seed data — AHLOA Milestone Columns
# ----------------------------------------------------------------
SEED_AHLOA_MILESTONE_COLUMNS = [
    # cpo — text presence check
    {"milestone_key": "cpo", "column_name": "ms_1555_construction_complete_cpo_custom_field",
     "column_role": "text", "logic": None, "sort_order": 1, "project_type": "ahloa"},

    # 3850 — single date
    {"milestone_key": "3850", "column_name": "pj_a_3850_bom_submitted_bom_in_bat_finish",
     "column_role": "date", "logic": None, "sort_order": 2, "project_type": "ahloa"},

    # 3875 — single date
    {"milestone_key": "3875", "column_name": "pj_a_3875_bom_received_bom_in_aims_finish",
     "column_role": "date", "logic": None, "sort_order": 3, "project_type": "ahloa"},

    # 3925 — single date
    {"milestone_key": "3925", "column_name": "pj_a_3925_msl_pickup_date_finish",
     "column_role": "date", "logic": None, "sort_order": 4, "project_type": "ahloa"},

    # 4000 — text presence check
    {"milestone_key": "4000", "column_name": "pj_a_4000_ll_ntp_received",
     "column_role": "text", "logic": None, "sort_order": 5, "project_type": "ahloa"},

    # 4075 — single date
    {"milestone_key": "4075", "column_name": "pj_a_4075_construction_ntp_submitted_to_gc_finish",
     "column_role": "date", "logic": None, "sort_order": 6, "project_type": "ahloa"},

    # 4100 — single date
    {"milestone_key": "4100", "column_name": "pj_a_4100_construction_ntp_accepted_by_gc_finish",
     "column_role": "date", "logic": None, "sort_order": 7, "project_type": "ahloa"},

    # spo_gc_cx — single date
    {"milestone_key": "spo_gc_cx", "column_name": "ms1555_construction_complete_spo_issued_date",
     "column_role": "date", "logic": None, "sort_order": 8, "project_type": "ahloa"},

    # crane — status check
    {"milestone_key": "crane", "column_name": "scoping_package_crane_required",
     "column_role": "status", "logic": json.dumps({"on_track": ["Yes", "No"], "delayed": ["null", "", None]}),
     "sort_order": 9, "project_type": "ahloa"},

    # talon_scoping — single date
    {"milestone_key": "talon_scoping", "column_name": "scoping_package_create_date",
     "column_role": "date", "logic": None, "sort_order": 10, "project_type": "ahloa"},

    # talon_scop — single date
    {"milestone_key": "talon_scop", "column_name": "ms_1557_punch_checklist_reviewed_and_submitted_to_tmobile_atl",
     "column_role": "date", "logic": None, "sort_order": 11, "project_type": "ahloa"},

    # nas_upload — date from external NAS table
    {"milestone_key": "nas_upload", "column_name": "nas_activity_end_date",
     "column_role": "date",
     "logic": json.dumps({"source_table": "nas_planned_outage_activity", "join_column": "nas_site_id", "filter": {"nas_project_category": "AHLOB"}}),
     "sort_order": 12, "project_type": "ahloa"},
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
        AhloaMilestoneDefinition.__table__,
        AhloaMilestoneColumn.__table__,
        AhloaConstraintThreshold.__table__,
    ])

    db: Session = ConfigSessionLocal()
    try:
        if db.query(MilestoneDefinition).count() == 0:
            for ms_data in SEED_MILESTONES:
                db.add(MilestoneDefinition(**ms_data))
            db.commit()
            logger.info("Seeded %d milestone definitions.", len(SEED_MILESTONES))
        else:
            # Sync back_days onto existing rows so the right-to-left actual view
            # has its canonical values without needing a re-seed.
            updated = 0
            for ms_data in SEED_MILESTONES:
                row = (
                    db.query(MilestoneDefinition)
                    .filter(MilestoneDefinition.key == ms_data["key"])
                    .first()
                )
                if row and row.back_days != ms_data.get("back_days"):
                    row.back_days = ms_data.get("back_days")
                    updated += 1
            if updated:
                db.commit()
                logger.info("Synced back_days on %d milestone definitions.", updated)

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

        # --- AHLOA seeds ---
        if db.query(AhloaMilestoneDefinition).count() == 0:
            for ms_data in SEED_AHLOA_MILESTONES:
                db.add(AhloaMilestoneDefinition(**ms_data))
            db.commit()
            logger.info("Seeded %d AHLOA milestone definitions.", len(SEED_AHLOA_MILESTONES))

        if db.query(AhloaMilestoneColumn).count() == 0:
            for col_data in SEED_AHLOA_MILESTONE_COLUMNS:
                db.add(AhloaMilestoneColumn(**col_data))
            db.commit()
            logger.info("Seeded %d AHLOA milestone columns.", len(SEED_AHLOA_MILESTONE_COLUMNS))
            
        if db.query(AhloaConstraintThreshold).count() == 0:
            for ct_data in SEED_AHLOA_CONSTRAINT_THRESHOLDS:
                db.add(AhloaConstraintThreshold(**ct_data))
            db.commit()
            logger.info("Seeded %d AHLOA constraint thresholds.", len(SEED_AHLOA_CONSTRAINT_THRESHOLDS))

    except Exception:
        db.rollback()
        logger.exception("Failed to seed milestone data.")
        raise
    finally:
        db.close()
