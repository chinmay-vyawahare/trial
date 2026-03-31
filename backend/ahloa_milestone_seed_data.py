"""
AHLOA Project — Milestone Seed Data (FOR VERIFICATION)

CX Start Date is CALCULATED per site:
  CX Start = Max(pj_p_3710_ran_entitlement_complete_finish,
                 pj_p_4075_construction_ntp_submitted_to_gc_finish) + 50 days

Each milestone has an offset (in weeks) backward from this CX start date.
Status logic: check if actual date/value meets the condition by expected date.

New columns needed on milestone_definitions table:
  - project_type  VARCHAR(20)  "NTM" | "MACRO" | "AHLOA"
  - offset_weeks  INTEGER      weeks offset from CX start (negative = before)
  - status_condition TEXT       human-readable status logic

New column needed on milestone_columns table:
  - project_type  VARCHAR(20)  "NTM" | "MACRO" | "AHLOA"

Source tables:
  - stg_ndpd_mbt_tmobile_macro_combined  (main staging table)
  - nas_planned_outage_activity           (NAS table — joined via nas_site_id)
"""

import json


# ================================================================
# AHLOA Milestone Definitions
# ================================================================
AHLOA_SEED_MILESTONES = [
    {
        "key": "cpo",
        "name": "CPO For Site",
        "project_type": "AHLOA",
        "sort_order": 1,
        "expected_days": 0,
        "offset_weeks": None,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Pre-CX Phase",
        "status_condition": "If ms_1555_construction_complete_cpo_custom_field is present (not blank) -> ON TRACK, else DELAYED",
    },
    {
        "key": "survey_eligible",
        "name": "Site Survey Scope Available (Y/N)",
        "project_type": "AHLOA",
        "sort_order": 2,
        "expected_days": 0,
        "offset_weeks": None,
        "depends_on": "cpo",
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Survey Phase",
        "status_condition": "IF CPO is present (Y) -> check ms_1321_talon_view_drone_svcs_cpo_custom_field. If not blank -> ON TRACK (eligible for survey), else DELAYED",
    },
    {
        "key": "survey_spo",
        "name": "Survey SPO Creation",
        "project_type": "AHLOA",
        "sort_order": 3,
        "expected_days": 0,
        "offset_weeks": None,
        "depends_on": "survey_eligible",
        "start_gap_days": 0,
        "task_owner": "PDM",
        "phase_type": "Survey Phase",
        "status_condition": "If ms_1321_talon_view_drone_svcs_spo_issued_date is present -> ON TRACK, else DELAYED",
    },
    {
        "key": "survey_complete",
        "name": "Survey Completion",
        "project_type": "AHLOA",
        "sort_order": 4,
        "expected_days": 14,
        "offset_weeks": -2,
        "depends_on": "survey_spo",
        "start_gap_days": 0,
        "task_owner": "Vendor",
        "phase_type": "Survey Phase",
        "status_condition": "Expected date = survey_spo date + 2 weeks. If ms_1321_talon_view_drone_svcs_actual <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "3850",
        "name": "BOM Ready (MS 3850)",
        "project_type": "AHLOA",
        "sort_order": 5,
        "expected_days": 0,
        "offset_weeks": -4,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Material Phase",
        "status_condition": "Expected date = CX Start - 4 weeks. If pj_a_3850_bom_submitted_bom_in_bat_finish <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "3875",
        "name": "BOM Material Available in MSL (MS 3875)",
        "project_type": "AHLOA",
        "sort_order": 6,
        "expected_days": 0,
        "offset_weeks": -1,
        "depends_on": "3850",
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "Material Phase",
        "status_condition": "Expected date = CX Start - 1 week. If pj_a_3875_bom_received_bom_in_aims_finish <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "3925",
        "name": "Material Pickup by GC (MS 3925)",
        "project_type": "AHLOA",
        "sort_order": 7,
        "expected_days": 0,
        "offset_weeks": -1,
        "depends_on": "3875",
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "Material Phase",
        "status_condition": "Expected date = CX Start - 1 week. If pj_a_3925_msl_pickup_date_finish <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "4000",
        "name": "LL NTP Ready (MS 4000)",
        "project_type": "AHLOA",
        "sort_order": 8,
        "expected_days": 0,
        "offset_weeks": -4,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "NTP Phase",
        "status_condition": "Expected date = CX Start - 4 weeks. If pj_a_4000_ll_ntp_received is present (not blank) -> ON TRACK, else DELAYED",
    },
    {
        "key": "4075",
        "name": "Overall NTP Ready (MS 4075)",
        "project_type": "AHLOA",
        "sort_order": 9,
        "expected_days": 0,
        "offset_weeks": -4,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "TMO",
        "phase_type": "NTP Phase",
        "status_condition": "Expected date = CX Start - 4 weeks. If pj_a_4075_construction_ntp_submitted_to_gc_finish <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "4100",
        "name": "Final NTP Ready (MS 4100)",
        "project_type": "AHLOA",
        "sort_order": 10,
        "expected_days": 0,
        "offset_weeks": -4,
        "depends_on": "4075",
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "NTP Phase",
        "status_condition": "Expected date = CX Start - 4 weeks. If pj_a_4100_construction_ntp_accepted_by_gc_finish <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "spo_gc_cx",
        "name": "SPO to GC for CX",
        "project_type": "AHLOA",
        "sort_order": 11,
        "expected_days": 0,
        "offset_weeks": -6,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "PDM",
        "phase_type": "Pre-CX Phase",
        "status_condition": "Expected date = CX Start - 6 weeks. If ms1555_construction_complete_spo_issued_date <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "crane",
        "name": "Crane",
        "project_type": "AHLOA",
        "sort_order": 12,
        "expected_days": 0,
        "offset_weeks": -2,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "GC",
        "phase_type": "CX Readiness Phase",
        "status_condition": "If scoping_package_crane_required = 'Yes' -> ON TRACK, else DELAYED",
    },
    {
        "key": "talon_scoping",
        "name": "Talon Session for Scoping",
        "project_type": "AHLOA",
        "sort_order": 13,
        "expected_days": 0,
        "offset_weeks": -2,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "SE-CoE",
        "phase_type": "CX Readiness Phase",
        "status_condition": "Expected date = CX Start - 2 weeks. If scoping_package_create_date <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "talon_scop",
        "name": "Talon Session for SCOP",
        "project_type": "AHLOA",
        "sort_order": 14,
        "expected_days": 0,
        "offset_weeks": -2,
        "depends_on": "talon_scoping",
        "start_gap_days": 0,
        "task_owner": "SE-CoE",
        "phase_type": "CX Readiness Phase",
        "status_condition": "Expected date = CX Start - 2 weeks. If ms_1557_punch_checklist_reviewed_and_submitted_to_tmobile_atl <= expected date -> ON TRACK, else DELAYED",
    },
    {
        "key": "nas_upload",
        "name": "Planned Activity Upload Status in NAS",
        "project_type": "AHLOA",
        "sort_order": 15,
        "expected_days": 0,
        "offset_weeks": -1,
        "depends_on": None,
        "start_gap_days": 0,
        "task_owner": "PM",
        "phase_type": "CX Readiness Phase",
        "status_condition": "Expected date = CX Start - 1 week. From nas_planned_outage_activity WHERE nas_project_category = 'AHLOB', join on nas_site_id. If nas_activity_end_date present -> ON TRACK, else DELAYED",
    },
]


# ================================================================
# AHLOA Milestone Columns
#
# Maps each milestone to its staging table column(s)
# ================================================================
AHLOA_SEED_MILESTONE_COLUMNS = [
    # --- cpo: text presence check ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "cpo", "project_type": "AHLOA",
     "column_name": "ms_1555_construction_complete_cpo_custom_field",
     "column_role": "text", "logic": None, "sort_order": 1},

    # --- survey_eligible: text presence check ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "survey_eligible", "project_type": "AHLOA",
     "column_name": "ms_1321_talon_view_drone_svcs_cpo_custom_field",
     "column_role": "text", "logic": None, "sort_order": 2},

    # --- survey_spo: date presence check ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "survey_spo", "project_type": "AHLOA",
     "column_name": "ms_1321_talon_view_drone_svcs_spo_issued_date",
     "column_role": "date", "logic": None, "sort_order": 3},

    # --- survey_complete: actual date vs SPO + 2 weeks ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "survey_complete", "project_type": "AHLOA",
     "column_name": "ms_1321_talon_view_drone_svcs_actual",
     "column_role": "date", "logic": None, "sort_order": 4},

    # --- 3850: BOM ready date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "3850", "project_type": "AHLOA",
     "column_name": "pj_a_3850_bom_submitted_bom_in_bat_finish",
     "column_role": "date", "logic": None, "sort_order": 5},

    # --- 3875: BOM material available date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "3875", "project_type": "AHLOA",
     "column_name": "pj_a_3875_bom_received_bom_in_aims_finish",
     "column_role": "date", "logic": None, "sort_order": 6},

    # --- 3925: Material pickup date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "3925", "project_type": "AHLOA",
     "column_name": "pj_a_3925_msl_pickup_date_finish",
     "column_role": "date", "logic": None, "sort_order": 7},

    # --- 4000: LL NTP ready (text presence) ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "4000", "project_type": "AHLOA",
     "column_name": "pj_a_4000_ll_ntp_received",
     "column_role": "text", "logic": None, "sort_order": 8},

    # --- 4075: Overall NTP date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "4075", "project_type": "AHLOA",
     "column_name": "pj_a_4075_construction_ntp_submitted_to_gc_finish",
     "column_role": "date", "logic": None, "sort_order": 9},

    # --- 4100: Final NTP date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "4100", "project_type": "AHLOA",
     "column_name": "pj_a_4100_construction_ntp_accepted_by_gc_finish",
     "column_role": "date", "logic": None, "sort_order": 10},

    # --- spo_gc_cx: SPO to GC date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "spo_gc_cx", "project_type": "AHLOA",
     "column_name": "ms1555_construction_complete_spo_issued_date",
     "column_role": "date", "logic": None, "sort_order": 11},

    # --- crane: status check (Yes/No) ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "crane", "project_type": "AHLOA",
     "column_name": "scoping_package_crane_required",
     "column_role": "status",
     "logic": json.dumps({"on_track": ["Yes"], "delayed": ["No", "", None]}),
     "sort_order": 12},

    # --- talon_scoping: scoping package create date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "talon_scoping", "project_type": "AHLOA",
     "column_name": "scoping_package_create_date",
     "column_role": "date", "logic": None, "sort_order": 13},

    # --- talon_scop: punch checklist date ---
    # Table: stg_ndpd_mbt_tmobile_macro_combined
    {"milestone_key": "talon_scop", "project_type": "AHLOA",
     "column_name": "ms_1557_punch_checklist_reviewed_and_submitted_to_tmobile_atl",
     "column_role": "date", "logic": None, "sort_order": 14},

    # --- nas_upload: from separate NAS table ---
    # Table: nas_planned_outage_activity (join on nas_site_id, filter nas_project_category = 'AHLOB')
    {"milestone_key": "nas_upload", "project_type": "AHLOA",
     "column_name": "nas_activity_end_date",
     "column_role": "date",
     "logic": json.dumps({
         "source_table": "nas_planned_outage_activity",
         "join_column": "nas_site_id",
         "filter": {"nas_project_category": "AHLOB"},
     }),
     "sort_order": 15},
]


# ================================================================
# AHLOA Gantt Config
#
# CX Start = Max(pj_p_3710_ran_entitlement_complete_finish,
#                pj_p_4075_construction_ntp_submitted_to_gc_finish) + 50 days
# ================================================================
AHLOA_SEED_GANTT_CONFIG = [
    {
        "config_key": "AHLOA_CX_START_OFFSET_DAYS",
        "config_value": "50",
        "description": "Days added after Max(3710, 4075) to get forecasted CX start date for AHLOA",
    },
    {
        "config_key": "AHLOA_CX_START_SOURCE_COLUMNS",
        "config_value": json.dumps([
            "pj_p_3710_ran_entitlement_complete_finish",
            "pj_p_4075_construction_ntp_submitted_to_gc_finish",
        ]),
        "description": "Columns to take Max of for AHLOA CX start calculation",
    },
]


# ================================================================
# Quick verification
# ================================================================
if __name__ == "__main__":
    print("=" * 90)
    print("AHLOA MILESTONE DEFINITIONS")
    print("=" * 90)
    print(f"{'#':<4} {'Key':<20} {'Name':<45} {'Offset':<10} {'Phase'}")
    print("-" * 90)
    for ms in AHLOA_SEED_MILESTONES:
        offset = f"{ms['offset_weeks']}w" if ms['offset_weeks'] is not None else "presence"
        print(f"{ms['sort_order']:<4} {ms['key']:<20} {ms['name']:<45} {offset:<10} {ms['phase_type']}")

    print()
    print("=" * 90)
    print("AHLOA MILESTONE COLUMNS")
    print("=" * 90)
    print(f"{'Key':<20} {'Column':<60} {'Role':<8} {'Table'}")
    print("-" * 90)
    for col in AHLOA_SEED_MILESTONE_COLUMNS:
        logic = json.loads(col["logic"]) if col["logic"] else None
        table = logic.get("source_table", "staging") if logic and isinstance(logic, dict) and "source_table" in logic else "staging"
        print(f"{col['milestone_key']:<20} {col['column_name']:<60} {col['column_role']:<8} {table}")

    print()
    print("=" * 90)
    print("CX START FORMULA")
    print("=" * 90)
    for cfg in AHLOA_SEED_GANTT_CONFIG:
        print(f"  {cfg['config_key']}: {cfg['config_value']}")
    print("  => CX Start = Max(pj_p_3710, pj_p_4075) + 50 days")
