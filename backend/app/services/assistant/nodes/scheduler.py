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
from app.services.gantt.queries import get_geo_hierarchy

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
- get_geolocation_hierarchy — fetch the full region → area → market hierarchy tree

**ALWAYS call the relevant tool** when:
- The user asks "what markets/regions/areas/sites/vendors are available?"
- You need to validate or match a user-provided filter value
- The user asks to change a filter and you need to confirm the value exists

## GEO HIERARCHY (Region → Area → Market)

The geographic filters follow a strict hierarchy: **Region → Area → Market**.
Every area belongs to exactly one region, and every market belongs to exactly one area.

**You have the `get_geolocation_hierarchy` tool** which returns the full mapping:
  {{"Central": {{"CO": ["Denver", "Colorado Springs"], "OK": ["Tulsa", "OKC"]}}, "South": {{"TX": ["Dallas", "Houston"]}}}}

### MANDATORY VALIDATION STEPS for any geo filter change (region, area, or market):

When the user asks to change region, area, or market, you MUST follow these steps IN ORDER:

**Step 1**: Call the relevant value tool (e.g. `get_available_markets`) to validate the value exists.
**Step 2**: Check CURRENT USER FILTERS — does the user have OTHER geo filters already set?
  - If the user has NO other geo filters set → skip to Step 4.
  - If the user HAS other geo filters set → proceed to Step 3.
**Step 3**: Call `get_geolocation_hierarchy` and cross-check:
  - If user has region and is changing area → verify the new area exists under that region.
  - If user has region and is changing market → verify the new market exists under that region.
  - If user has area and is changing market → verify the new market exists under that area.
  - If user is changing region and has area/market → verify existing area/market exist under the new region.
  - **If there is a MISMATCH** → do NOT save. Instead, warn the user with empty actions:
    Example: {{"message": "The market 'Chicago' does not belong to your current region 'South'. In the hierarchy, Chicago is under the 'Central' region → 'IL' area. Would you like me to update your region to 'Central' and area to 'IL' along with the market?", "actions": []}}
  - **If the user confirms** (e.g. "yes") → update ALL conflicting filters together in one save.
  - **If there is NO mismatch** → proceed to Step 4.
**Step 4**: Save the filter with a POST action.

## AVAILABLE API ENDPOINTS:

{api_registry}

## CURRENT USER FILTERS:

{user_filters}

## RECENT CONVERSATION SUMMARY:

{chat_summary}

## CRITICAL — CONFIRMATIONS:

When the user says "yes", "confirm", "do it", "go ahead", "correct", or similar short
confirmations, look at the PREVIOUS assistant message in the conversation history.
If the previous assistant message proposed a specific filter change or asked the user to
confirm, IMMEDIATELY execute that action WITHOUT re-validating or calling any tools again.
You already validated it in the previous turn. Just return the save action directly.

## RULES:

1. Always respond with a JSON object:
   - "message": a human-readable explanation that MUST ALWAYS be present and descriptive.
     When listing filter values, include a friendly intro like "Here are the available markets:" followed by the list.
     When changing a filter, confirm what was changed.
     NEVER leave the message empty or vague — the message is displayed directly to the user in the UI.
   - "actions": list of API calls for the frontend (can be empty if just answering a question)

2. Each action must have:
   - "method": GET, POST, or DELETE
   - "endpoint": full path (replace {{user_id}} with actual value)
   - "params": dict of values (only include non-null values)

3. **CRITICAL — ONLY change what the user explicitly asked for:**
   - If user says "change market to Dallas", ONLY include "market" and "user_id" in params.
   - If user says "set region to South", ONLY include "region" and "user_id" in params.
   - NEVER add extra filters that the user did not mention in their request.
   - Only include the filter(s) the user explicitly mentioned + user_id. Nothing else.

4. **IMPORTANT — region, market, and area are LISTS (arrays), not strings:**
   - region: always a list, e.g. ["South"] or ["South", "Northeast"]
   - market: always a list, e.g. ["Dallas"] or ["Dallas", "NYC"]
   - area: always a list, e.g. ["Urban"] or ["Urban", "Rural"]
   - plan_type_include: always a list, e.g. ["New Build", "FOA"]
   - vendor and site_id: remain strings
   - regional_dev_initiatives: remains a string

5. When user asks to change/set a geo filter (region, area, or market):
   - **YOU MUST follow the MANDATORY VALIDATION STEPS above (Steps 1–4).**
   - Step 1: Call the value tool to validate the value exists and match it exactly.
   - Step 2–3: If other geo filters exist, call `get_geolocation_hierarchy` and cross-check.
     If mismatch → warn with empty actions. If no mismatch → proceed.
   - Step 4: Return a save_user_filters POST action with ONLY user_id + changed param(s).
   - Example: {{"message": "Market filter updated to Dallas.", "actions": [{{"method": "POST", "endpoint": "/api/v1/schedular/user-filters", "params": {{"user_id": "<actual_user_id>", "market": ["Dallas"]}}}}]}}
   - If the value does NOT exactly match but is CLOSE (typo):
     * Suggest the closest match as a follow-up question
     * Example: {{"message": "Did you mean 'South'? Please confirm.", "actions": []}}
   - If no match at all, inform the user and list available options.

5b. When user asks to change a NON-geo filter (vendor, site_id):
   - Call the relevant value tool, match, and save. No hierarchy check needed.

5c. When user asks to SKIP a prerequisite/milestone:
   - Call `get_available_prerequisites` to fetch all milestones with their current skip status.
   - Match the user's request to the correct milestone by name (fuzzy match OK to find it).
   - **CRITICAL: Use the EXACT `key` value from the tool result in the action params. Never modify, rename, or guess the key. The key must match the DB exactly (e.g. "steel", "3925", "site_walk", "cpo").**
   - If the milestone is already skipped, inform the user.
   - If not skipped, return a POST action to skip it:
     Example: {{"message": "Skipping 'Steel Received (If applicable)' prerequisite. Downstream milestones will recalculate.", "actions": [{{"method": "POST", "endpoint": "/api/v1/schedular/skip-prerequisites", "params": {{"user_id": "<actual_user_id>", "milestone_key": "steel"}}}}]}}

5d. When user asks to UNSKIP a prerequisite or asks which prerequisites are skipped:
   - Call `get_available_prerequisites` to fetch current status.
   - **CRITICAL: Always use the EXACT `key` from the tool result, not the user's wording.**
   - To unskip: return a DELETE action:
     Example: {{"message": "Un-skipping 'Steel Received (If applicable)' prerequisite.", "actions": [{{"method": "DELETE", "endpoint": "/api/v1/schedular/skip-prerequisites/<user_id>/steel", "params": {{"user_id": "<actual_user_id>", "milestone_key": "steel"}}}}]}}
   - To unskip all: {{"method": "DELETE", "endpoint": "/api/v1/schedular/skip-prerequisites/<user_id>", "params": {{"user_id": "<actual_user_id>"}}}}
   - To list skipped: show the skipped milestones in the message with empty actions.

6. When user asks to change a gate check (plan_type_include or regional_dev_initiatives):
   - Use the same POST `/api/v1/schedular/user-filters` endpoint
   - Example: {{"message": "Plan type filter set to New Build.", "actions": [{{"method": "POST", "endpoint": "/api/v1/schedular/user-filters", "params": {{"user_id": "<actual_user_id>", "plan_type_include": ["New Build"]}}}}]}}

7. When user asks "what markets are available" or "list regions" or asks about filter options:
   - Call the relevant tool to get the current values from the database
   - Return the list in the "message" field with a friendly intro and the complete list
   - The "actions" array should be empty
   - Format the list as comma-separated values for clean display

8. If user asks for their current filters, return the filters from CURRENT USER FILTERS
   in the message field with a clear explanation and do not return an action.

9. When user asks to clear, remove, or reset all their filters:
   - Return the clear_user_filters action with method DELETE and the user-filters endpoint
   - Example: {{"message": "All your filters have been cleared.", "actions": [{{"method": "DELETE", "endpoint": "/api/v1/schedular/user-filters/{user_id}", "params": {{"user_id": "<actual_user_id>"}}}}]}}
   - Replace {user_id} in the endpoint with the actual user_id value

10. Only include params that have actual values. Skip null/empty params.

11. ONLY respond with valid JSON. No markdown, no code blocks.

12. Use the RECENT CONVERSATION SUMMARY and the conversation history messages to maintain context from prior messages.

13. NEVER call the same tool more than once in a conversation. If you already have the tool results from a previous round, use them directly. Do not loop.

14. When handling a confirmation ("yes", "correct", etc.), do NOT call any tools. Just return the action based on what was previously discussed.

15. NEVER include action details (endpoints, params, JSON) in the "message" field. The message is shown to the user in the UI — keep it human-readable. Actions go ONLY in the "actions" array.
"""

MAX_TOOL_ROUNDS = 7


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


def _exec_get_geolocation_hierarchy(db: Session) -> dict:
    """Return geo hierarchy grouped as {region: {area: [markets]}}."""
    rows = get_geo_hierarchy(db)
    hierarchy: dict[str, dict[str, list[str]]] = {}
    for r in rows:
        region = r["region"]
        area = r["area"]
        market = r["market"]
        hierarchy.setdefault(region, {}).setdefault(area, []).append(market)
    return hierarchy


def _exec_get_available_prerequisites(db: Session, user_id: str = None) -> list[dict]:
    """Fetch all milestones with their skip status for the user."""
    from app.models.prerequisite import MilestoneDefinition, UserSkippedPrerequisite

    milestones = (
        db.query(MilestoneDefinition)
        .filter(MilestoneDefinition.is_skipped == False)
        .order_by(MilestoneDefinition.sort_order)
        .all()
    )

    skipped_keys = set()
    if user_id:
        rows = (
            db.query(UserSkippedPrerequisite.milestone_key)
            .filter(UserSkippedPrerequisite.user_id == user_id)
            .all()
        )
        skipped_keys = {r[0] for r in rows}

    return [
        {
            "key": ms.key,
            "name": ms.name,
            "is_skipped": ms.key in skipped_keys,
        }
        for ms in milestones
    ]


TOOL_EXECUTORS = {
    "get_available_regions": _exec_get_available_regions,
    "get_available_markets": _exec_get_available_markets,
    "get_available_areas": _exec_get_available_areas,
    "get_available_sites": _exec_get_available_sites,
    "get_available_vendors": _exec_get_available_vendors,
    "get_available_plan_types": _exec_get_available_plan_types,
    "get_available_dev_initiatives": _exec_get_available_dev_initiatives,
    "get_geolocation_hierarchy": _exec_get_geolocation_hierarchy,
    "get_available_prerequisites": _exec_get_available_prerequisites,
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
    recent_messages: list[dict] | None = None,
    config_db: Session = None,
) -> dict:
    """Handle scheduling-related requests via LLM with tool calling."""
    client = get_openai_client()
    model = LLM_MODEL

    logger.info("  [SCHEDULER] Starting scheduler agent ...")
    logger.info("  [SCHEDULER] Model: %s", model)

    system_prompt = _build_scheduler_prompt(user_id, user_filters, chat_summary)
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Include last 6 messages as actual conversation turns for context
    if recent_messages:
        for msg in recent_messages[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

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
                        if fn_name == "get_available_prerequisites":
                            result = executor(config_db or db, user_id=user_id)
                        else:
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
        # LLM sometimes embeds JSON inside text — try to extract it
        # Find the last '{' that starts a JSON with "message" and "actions"
        import re
        result = None
        # Try progressively from each '{' in the string
        for m in re.finditer(r'\{', raw):
            candidate = raw[m.start():]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "message" in parsed:
                    result = parsed
                    logger.info("  [SCHEDULER] Extracted embedded JSON from response")
                    break
            except json.JSONDecodeError:
                continue
        if result is None:
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
