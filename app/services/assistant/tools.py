"""
API registry + LLM tool definitions for the AI assistant.

Two things live here:
1. API_REGISTRY  — endpoints the LLM can tell the *frontend* to call.
2. FILTER_TOOLS  — OpenAI function-calling tools the LLM can invoke
   *during* the conversation to fetch filter values on demand,
   so we never dump 3 000+ site IDs into the system prompt.
"""

# ── API REGISTRY (unchanged — frontend-facing endpoints) ────────────────

API_REGISTRY = {
    "get_gantt_charts": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/gantt-charts",
        "description": "Fetch Gantt chart data — sites with milestone timelines, statuses, delays. When user_id is passed with filters, the filters are auto-saved for that user.",
        "params": {
            "region": "string | null",
            "market": "string | null",
            "site_id": "string | null",
            "vendor": "string | null",
            "area": "string | null",
            "user_id": "string | null",
            "limit": "int | null",
            "offset": "int | null",
        },
    },
    "get_dashboard": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/gantt-charts/dashboard",
        "description": "Fetch dashboard summary — on-track/in-progress/critical site counts and percentages.",
        "params": {
            "region": "string | null",
            "market": "string | null",
            "vendor": "string | null",
            "area": "string | null",
            "user_id": "string | null",
        },
    },
    "get_user_filters": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/user-filters/{user_id}",
        "description": "Get currently saved filters for a user.",
        "params": {"user_id": "string — path param"},
    },
    "get_user_gate_checks": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/gate-checks/{user_id}",
        "description": "Get saved gate checks for a user.",
        "params": {"user_id": "string — path param"},
    },
    "get_constraints": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/constraints",
        "description": "Get all constraint thresholds (status rules).",
        "params": {},
    },
    "get_constraints_milestone": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/constraints/milestone",
        "description": "Get milestone-level constraint thresholds only.",
        "params": {},
    },
    "get_constraints_overall": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/constraints/overall",
        "description": "Get dashboard-level constraint thresholds only.",
        "params": {},
    },
    "export_gantt_csv": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/export/gantt-csv",
        "description": "Export gantt chart data as a downloadable CSV file. If user_id is provided, applies that user's saved filters. If not, exports all sites.",
        "params": {
            "user_id": "string | null",
        },
    },
}

# ── LLM TOOL DEFINITIONS (OpenAI function-calling format) ──────────────
# The LLM calls these *during* a conversation turn to fetch filter values
# on demand instead of having them all pre-loaded in the system prompt.

FILTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_available_regions",
            "description": "Fetch the list of all available region values from the database. Call this when the user asks about regions or you need to validate a region value.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_markets",
            "description": "Fetch the list of all available market values from the database. Call this when the user asks about markets or you need to validate a market value.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_areas",
            "description": "Fetch the list of all available area values from the database. Call this when the user asks about areas or you need to validate an area value.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_sites",
            "description": "Fetch the list of all available site IDs from the database. Call this when the user asks about sites or you need to validate a site ID.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_vendors",
            "description": "Fetch the list of all available vendor/general-contractor values from the database. Call this when the user asks about vendors or you need to validate a vendor value.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_plan_types",
            "description": "Fetch the list of all available plan type values (por_plan_type) from the database. Call this when the user asks about plan types or gate checks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_dev_initiatives",
            "description": "Fetch the list of all available regional development initiative values from the database. Call this when the user asks about dev initiatives or gate checks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
