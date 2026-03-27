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
    "get_user_filters": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/user-filters/{user_id}",
        "description": "Get currently saved filters for a user.",
        "params": {"user_id": "string — path param"},
    },
    "clear_user_filters": {
        "method": "DELETE",
        "endpoint": "/api/v1/schedular/user-filters/{user_id}",
        "description": "Clear/remove all saved filters for a user. Use when user asks to remove, clear, or reset their filters.",
        "params": {"user_id": "string — path param"},
    },
    "save_user_filters": {
        "method": "POST",
        "endpoint": "/api/v1/schedular/user-filters",
        "description": "Save or update all user filters and gate checks in a single call. Upserts — creates if not exists, updates otherwise. Use this when the user asks to change/set any filter or gate check.",
        "params": {
            "user_id": "string — required",
            "region": "list[string] | null — e.g. [\"South\", \"Northeast\"]",
            "market": "list[string] | null — e.g. [\"Dallas\", \"NYC\"]",
            "vendor": "string | null",
            "site_id": "string | null",
            "area": "list[string] | null — e.g. [\"Urban\"]",
            "plan_type_include": "list[string] | null — gate check, e.g. [\"New Build\", \"FOA\"]",
            "regional_dev_initiatives": "string | null — gate check, free-text ILIKE pattern",
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
    {
        "type": "function",
        "function": {
            "name": "get_geolocation_hierarchy",
            "description": "Fetch the complete geographic hierarchy (region → area → market) from the database. Returns a list of {region, area, market} mappings. ALWAYS call this when the user changes a geo filter (region, area, or market) and they already have other geo filters set — use it to check if the new value is consistent with the existing geo filters.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
