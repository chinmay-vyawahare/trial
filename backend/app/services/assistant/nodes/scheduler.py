"""
Scheduler node — handles all scheduling-related requests.

This is the existing chatbot logic: LLM with tool-calling that returns
API endpoints + params for the frontend to call.
"""

import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import STAGING_TABLE
from app.services.assistant.llm import get_openai_client, LLM_MODEL
from app.services.assistant.tools import API_REGISTRY, FILTER_TOOLS
from app.services.gantt import get_filter_options

logger = logging.getLogger(__name__)

_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)

SCHEDULER_PROMPT = """You are a filter management assistant for Nokia's construction project tracker.

Your ONLY job is to help users **view and update their filters** (region, market, area,
site, vendor, plan type, dev initiatives) and return the correct API call for the
frontend to execute.

You do NOT execute anything. You only return instructions for the frontend.

## TOOLS YOU CAN CALL

You have tools to fetch available filter values from the database in real time:
- get_available_regions — fetch all region values
- get_available_markets — fetch all market values
- get_available_areas — fetch all area values
- get_available_sites — fetch all site IDs
- get_available_vendors — fetch all vendor/GC values
- get_available_plan_types — fetch all plan type values
- get_available_dev_initiatives — fetch all dev initiative values

**ALWAYS call the relevant tool** when:
- The user asks "what markets/regions/areas/sites/vendors are available?"
- You need to validate or match a user-provided filter value
- The user asks to change a filter and you need to confirm the value exists

## AVAILABLE API ENDPOINTS:

{api_registry}

## CURRENT USER FILTERS:

{user_filters}

## RECENT CONVERSATION SUMMARY:

{chat_summary}

## RULES:

1. Always respond with a JSON object:
   - "message": a human-readable explanation that MUST ALWAYS be present and descriptive.
     When listing filter values, include a friendly intro like "Here are the available markets:" followed by the list.
     When changing a filter, confirm what was changed.
     NEVER leave the message empty or vague — the message is displayed directly to the user in the UI.
   - "actions": list of API calls for the frontend (can be empty if just answering a question)

2. Each action must have:
   - "method": GET
   - "endpoint": full path (replace {{user_id}} with actual value)
   - "params": query params dict (only include non-null values)

3. **CRITICAL — ONLY change what the user explicitly asked for:**
   - If user says "change market to Dallas", ONLY include "market" and "user_id" in params.
   - If user says "set region to South", ONLY include "region" and "user_id" in params.
   - NEVER add extra filters that the user did not mention in their request.
   - The backend merges with saved filters automatically — you do NOT need to re-send existing filters.
   - Only include the filter(s) the user explicitly mentioned + user_id. Nothing else.

4. When user asks to change a filter (e.g. "change market to Dallas"):
   - First call the relevant tool (e.g. get_available_markets) to get the real values
   - Match the user's input to the exact value from the tool results
   - Return the gantt-charts endpoint with ONLY user_id + the changed filter param
   - The backend auto-saves filters when user_id is provided
   - Do NOT return a separate save/update call
   - If the user's input does NOT exactly match any available value but is CLOSE (e.g. typo):
     * Suggest the closest matching value(s) as a follow-up question
     * Example: {{"message": "Did you mean 'South'? Please confirm and I'll update the region filter.", "actions": []}}
   - If multiple values could match, list all options
   - If no match at all, inform the user and list available options for that filter

5. When user asks "what markets are available" or "list regions" or asks about filter options:
   - Call the relevant tool to get the current values from the database
   - Return the list in the "message" field with a friendly intro and the complete list
   - The "actions" array should be empty
   - Format the list as comma-separated values for clean display

6. If user asks for their current filters, return the filters from CURRENT USER FILTERS
   in the message field with a clear explanation and do not return an action.

7. When user asks to clear, remove, or reset all their filters:
   - Return the clear_user_filters action with method DELETE and the user-filters endpoint
   - Example: {{"message": "All your filters have been cleared.", "actions": [{{"method": "DELETE", "endpoint": "/api/v1/schedular/user-filters/{user_id}", "params": {{"user_id": "<actual_user_id>"}}}}]}}
   - Replace {user_id} in the endpoint with the actual user_id value

8. Only include params that have actual values. Skip null/empty params.

9. ONLY respond with valid JSON. No markdown, no code blocks.

10. Use the RECENT CONVERSATION SUMMARY to maintain context from prior messages.
"""

MAX_TOOL_ROUNDS = 5


# ── Tool execution helpers ─────────────────────────────────────────────

def _exec_get_available_regions(db: Session) -> list[str]:
    filters = get_filter_options(db)
    return filters.get("regions", [])


def _exec_get_available_markets(db: Session) -> list[str]:
    filters = get_filter_options(db)
    return filters.get("markets", [])


def _exec_get_available_areas(db: Session) -> list[str]:
    filters = get_filter_options(db)
    return filters.get("areas", [])


def _exec_get_available_sites(db: Session) -> list[str]:
    filters = get_filter_options(db)
    return filters.get("site_ids", [])


def _exec_get_available_vendors(db: Session) -> list[str]:
    filters = get_filter_options(db)
    return filters.get("vendors", [])


def _exec_get_available_plan_types(db: Session) -> list[str]:
    rows = db.execute(text(
        f"SELECT DISTINCT por_plan_type FROM {STAGING_TABLE} "
        f"WHERE {_BASE_WHERE} AND por_plan_type IS NOT NULL ORDER BY por_plan_type"
    ))
    return [r[0] for r in rows]


def _exec_get_available_dev_initiatives(db: Session) -> list[str]:
    rows = db.execute(text(
        f"SELECT DISTINCT por_regional_dev_initiatives FROM {STAGING_TABLE} "
        f"WHERE {_BASE_WHERE} AND por_regional_dev_initiatives IS NOT NULL ORDER BY por_regional_dev_initiatives"
    ))
    return [r[0] for r in rows]


TOOL_EXECUTORS = {
    "get_available_regions": _exec_get_available_regions,
    "get_available_markets": _exec_get_available_markets,
    "get_available_areas": _exec_get_available_areas,
    "get_available_sites": _exec_get_available_sites,
    "get_available_vendors": _exec_get_available_vendors,
    "get_available_plan_types": _exec_get_available_plan_types,
    "get_available_dev_initiatives": _exec_get_available_dev_initiatives,
}


def _build_scheduler_prompt(user_id: str, user_filters: dict, chat_summary: str) -> str:
    registry_text = json.dumps(API_REGISTRY, indent=2)
    user_filters_text = json.dumps(user_filters, indent=2)

    prompt = SCHEDULER_PROMPT.replace("{api_registry}", registry_text)
    prompt = prompt.replace("{user_filters}", user_filters_text)
    prompt = prompt.replace("{chat_summary}", chat_summary)
    prompt += f"\n\nCurrent user_id: {user_id}"
    return prompt


def handle_scheduler(
    user_message: str,
    user_id: str,
    user_filters: dict,
    chat_summary: str,
    db: Session,
) -> dict:
    """Handle scheduling-related requests via LLM with tool calling."""
    client = get_openai_client()
    model = LLM_MODEL

    logger.info("  [SCHEDULER] Starting scheduler agent ...")
    logger.info("  [SCHEDULER] Model: %s", model)

    system_prompt = _build_scheduler_prompt(user_id, user_filters, chat_summary)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.info("  [SCHEDULER] LLM call round %d/%d ...", round_num + 1, MAX_TOOL_ROUNDS)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=FILTER_TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            messages.append(choice.message)
            tool_names = [tc.function.name for tc in choice.message.tool_calls]
            logger.info(
                "  [SCHEDULER] LLM requested %d tool call(s): %s",
                len(choice.message.tool_calls), ", ".join(tool_names),
            )

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                executor = TOOL_EXECUTORS.get(fn_name)

                if executor:
                    try:
                        result = executor(db)
                        tool_result = json.dumps(result)
                        result_preview = tool_result[:150] + "..." if len(tool_result) > 150 else tool_result
                        logger.info(
                            "  [SCHEDULER]   -> %s : OK (%d chars) %s",
                            fn_name, len(tool_result), result_preview,
                        )
                    except Exception as e:
                        logger.error("  [SCHEDULER]   -> %s : FAILED — %s", fn_name, e)
                        tool_result = json.dumps({"error": str(e)})
                else:
                    logger.warning("  [SCHEDULER]   -> %s : UNKNOWN TOOL", fn_name)
                    tool_result = json.dumps({"error": f"Unknown tool: {fn_name}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
            continue

        raw = choice.message.content.strip() if choice.message.content else ""
        logger.info("  [SCHEDULER] LLM final response (round %d)", round_num + 1)
        break
    else:
        logger.warning("  [SCHEDULER] Exhausted %d tool rounds — returning fallback", MAX_TOOL_ROUNDS)
        raw = json.dumps({
            "message": "I had trouble processing your request. Please try again.",
            "actions": [],
        })

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("  [SCHEDULER] Failed to parse LLM JSON, raw: %s", raw[:200])
        result = {"message": raw, "actions": []}

    if not result.get("message"):
        result["message"] = "Here is the information you requested."

    result.setdefault("actions", [])
    logger.info(
        "  [SCHEDULER] Done — message: \"%s\" | actions: %d",
        result["message"][:100], len(result["actions"]),
    )
    return result
