MILESTONES = [
    {
        "key": "3710",
        "name": "Entitlement Complete (MS 3710)",
        "sort_order": 1,
        "expected_days": 0,
        "depends_on": None,
        "actual_field": "a_3710_raw",
    },
    {
        "key": "pre_ntp",
        "name": "Pre-NTP Document Received",
        "sort_order": 2,
        "expected_days": 2,
        "depends_on": "3710",
        "actual_field": "a_pre_ntp_raw",
    },
    {
        "key": "site_walk",
        "name": "Site Walk Performed",
        "sort_order": 3,
        "expected_days": 7,
        "depends_on": "pre_ntp",
        "actual_field": "site_walk",  # special: min of manual & drone
    },
    {
        "key": "1323",
        "name": "Ready for Scoping (MS 1323)",
        "sort_order": 4,
        "expected_days": 3,
        "depends_on": "site_walk",
        "actual_field": "a_ready_scoping_raw",
    },
    {
        "key": "1327",
        "name": "Scoping Validated by GC (MS 1327)",
        "sort_order": 5,
        "expected_days": 7,
        "depends_on": "1323",
        "actual_field": "a_scoping_validated_raw",
    },
    {
        "key": "3850",
        "name": "BOM in BAT (MS 3850)",
        "sort_order": 6,
        "expected_days": 14,
        "depends_on": ["3710", "1327"],  # max of both
        "actual_field": "a_3850_raw",
    },
    {
        "key": "3875",
        "name": "BOM Received in AIMS (MS 3875)",
        "sort_order": 7,
        "expected_days": 21,
        "depends_on": "3850",
        "actual_field": "a_3875_raw",
    },
    {
        "key": "steel",
        "name": "Steel Received (If applicable)",
        "sort_order": 8,
        "expected_days": 14,
        "depends_on": "1327",
        "actual_field": "steel",  # special: uses a_steel_date_raw + a_steel_status
    },
    {
        "key": "3925",
        "name": "Material Pickup by GC (MS 3925)",
        "sort_order": 9,
        "expected_days": 5,
        "depends_on": "steel",
        "actual_field": "a_3925_raw",
    },
    {
        "key": "quote",
        "name": "Quote Submitted to Customer",
        "sort_order": 10,
        "expected_days": 7,
        "depends_on": "1327",
        "actual_field": "a_quote_submitted_raw",
    },
    {
        "key": "cpo",
        "name": "CPO Available",
        "sort_order": 11,
        "expected_days": 14,
        "depends_on": "quote",
        "actual_field": "a_cpo_raw",
        "is_text": True,
    },
    {
        "key": "spo",
        "name": "SPO Issued",
        "sort_order": 12,
        "expected_days": 5,
        "depends_on": "cpo",
        "actual_field": "a_spo_raw",
    },
    {
        "key": "access",
        "name": "Access Confirmation",
        "sort_order": 13,
        "expected_days": 7,
        "depends_on": "1327",
        "actual_field": "a_access_raw",
        "is_text": True,
    },
    {
        "key": "ntp",
        "name": "NTP Received",
        "sort_order": 14,
        "expected_days": 7,
        "depends_on": "1327",
        "actual_field": "a_ntp_raw",
    },
]

# ----------------------------------------------------------------
# All Prerequisites Complete calculation
# Each tail milestone has extra offset days after its planned finish
# before it counts as "done" for CX Start
# ----------------------------------------------------------------
PREREQ_TAILS = [
    {"key": "3925",   "offset_days": 4},
    {"key": "steel",  "offset_days": 7},
    {"key": "spo",    "offset_days": 5},
    {"key": "access", "offset_days": 7},
    {"key": "ntp",    "offset_days": 7},
]

# Days after All Prerequisites Complete → Forecasted CX Start
CX_START_OFFSET_DAYS = 4
