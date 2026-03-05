"""
API registry for the AI assistant.

Only data-fetching endpoints. The LLM picks which endpoint the frontend
should call and fills in the right query params based on user's request.

Note: gantt-charts and dashboard endpoints auto-save filters when user_id
is provided, so no separate user-filters save call is needed.
"""

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
    "get_regions": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/filters/regions",
        "description": "Get all distinct region values.",
        "params": {},
    },
    "get_markets": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/filters/markets",
        "description": "Get all distinct market values.",
        "params": {},
    },
    "get_areas": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/filters/areas",
        "description": "Get all distinct area values.",
        "params": {},
    },
    "get_sites": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/filters/sites",
        "description": "Get all distinct site IDs.",
        "params": {},
    },
    "get_vendors": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/filters/vendors",
        "description": "Get all distinct vendor/GC values.",
        "params": {},
    },
    "get_user_filters": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/user-filters/{user_id}",
        "description": "Get currently saved filters for a user.",
        "params": {"user_id": "string — path param"},
    },
    "get_gate_check_plan_types": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/gate-checks/por_plan_type",
        "description": "Get all distinct plan type values.",
        "params": {},
    },
    "get_gate_check_dev_initiatives": {
        "method": "GET",
        "endpoint": "/api/v1/schedular/gate-checks/por_regional_dev_initiatives",
        "description": "Get all distinct regional dev initiatives values.",
        "params": {},
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
}
