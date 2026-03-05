"""
AI Assistant service — ChatOpenAI with tool calling.

The LLM does NOT execute anything directly. It returns API endpoint(s) + params
that the frontend should call.

Instead of dumping all filter values (3000+ sites) into the system prompt,
the LLM has **tools** it can call on demand to fetch only the filter data
it needs (regions, markets, areas, sites, vendors, plan types, dev initiatives).

Chat history is persisted per user_id in the chat_history table.
The last 5 message pairs are summarized and included in the system prompt.
"""

import json
import logging
import os
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text

from .tools import API_REGISTRY, FILTER_TOOLS
from app.services.gantt import get_filter_options
from app.models.prerequisite import UserFilter, ChatHistory

logger = logging.getLogger(__name__)

_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)

SYSTEM_PROMPT = """You are a scheduling assistant for Nokia's construction project tracker.

Your job: take the user's natural language request and return the API endpoint
the frontend should call, with the correct query params filled in.

You do NOT execute anything. You only return instructions for the frontend.

## TOOLS YOU CAN CALL

You have access to tools that fetch filter values from the database in real time:
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
     When showing dashboard, explain what data will be shown.
     NEVER leave the message empty or vague — the message is displayed directly to the user in the UI.
   - "actions": list of API calls for the frontend (can be empty if just answering a question)

2. Each action must have:
   - "method": GET
   - "endpoint": full path (replace {{user_id}} with actual value)
   - "params": query params dict (only include non-null values)

3. **CRITICAL — ONLY change what the user explicitly asked for:**
   - If user says "change market to Dallas", ONLY include "market" and "user_id" in params. Do NOT add region, vendor, area, or any other filter.
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
   - If the user's input does NOT exactly match any available value but is CLOSE (e.g. typo like "southh" for "South", or partial match like "dal" for "Dallas"):
     * Suggest the closest matching value(s) as a follow-up question
     * Example: {{"message": "Did you mean 'South'? Please confirm and I'll update the region filter.", "actions": []}}
   - If multiple values could match, list all options:
     * Example: {{"message": "I found multiple matches. Did you mean one of these? 1. New York, 2. New Jersey. Please specify which one.", "actions": []}}
   - If no match at all, inform the user and list available options for that filter

5. When user asks "what markets are available" or "list regions" or asks about filter options:
   - Call the relevant tool to get the current values from the database
   - Return the list in the "message" field with a friendly intro and the complete list
   - The "actions" array should be empty
   - Format the list as comma-separated values for clean display (e.g. "Dallas, Houston, Chicago, ...")

6. When user asks "show dashboard" or "how are things looking":
   - Return the dashboard endpoint with user_id

7. When user asks about constraints or thresholds:
   - Return the constraints endpoint

8. Only include params that have actual values. Skip null/empty params.

9. ONLY respond with valid JSON. No markdown, no code blocks.

10. Use the RECENT CONVERSATION SUMMARY to maintain context from prior messages.

11. If user asked for the user's current filters, return the filters in the message field with a clear explanation and do not return an action.
"""


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
        f"SELECT DISTINCT por_plan_type FROM public.stg_ndpd_mbt_tmobile_macro_combined "
        f"WHERE {_BASE_WHERE} AND por_plan_type IS NOT NULL ORDER BY por_plan_type"
    ))
    return [r[0] for r in rows]


def _exec_get_available_dev_initiatives(db: Session) -> list[str]:
    rows = db.execute(text(
        f"SELECT DISTINCT por_regional_dev_initiatives FROM public.stg_ndpd_mbt_tmobile_macro_combined "
        f"WHERE {_BASE_WHERE} AND por_regional_dev_initiatives IS NOT NULL ORDER BY por_regional_dev_initiatives"
    ))
    return [r[0] for r in rows]


# Map tool name → executor function
TOOL_EXECUTORS = {
    "get_available_regions": _exec_get_available_regions,
    "get_available_markets": _exec_get_available_markets,
    "get_available_areas": _exec_get_available_areas,
    "get_available_sites": _exec_get_available_sites,
    "get_available_vendors": _exec_get_available_vendors,
    "get_available_plan_types": _exec_get_available_plan_types,
    "get_available_dev_initiatives": _exec_get_available_dev_initiatives,
}


# ── Existing helpers ───────────────────────────────────────────────────

def _get_user_filters(config_db: Session, user_id: str) -> dict:
    """Fetch currently saved filters for this user."""
    row = config_db.query(UserFilter).filter(UserFilter.user_id == user_id).first()
    if not row:
        return {"status": "No saved filters"}

    result = {
        "region": row.region,
        "market": row.market,
        "vendor": row.vendor,
        "site_id": row.site_id,
        "area": row.area,
        "plan_type_include": None,
        "regional_dev_initiatives": row.regional_dev_initiatives,
    }
    if row.plan_type_include:
        try:
            result["plan_type_include"] = json.loads(row.plan_type_include)
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def _get_recent_messages(config_db: Session, user_id: str, limit: int = 10) -> list[dict]:
    """Load last N messages (5 pairs = 10 rows) from chat_history table."""
    rows = (
        config_db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def _summarize_history(messages: list[dict]) -> str:
    """Build a concise summary of recent messages for the system prompt."""
    if not messages:
        return "No previous conversation."

    lines = []
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg["content"]
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"- {role}: {content}")

    return "\n".join(lines)


def _save_messages(config_db: Session, user_id: str, user_msg: str, assistant_msg: str):
    """Save user and assistant messages to chat_history table."""
    config_db.add(ChatHistory(user_id=user_id, role="user", content=user_msg))
    config_db.add(ChatHistory(user_id=user_id, role="assistant", content=assistant_msg))
    config_db.commit()


def _build_system_prompt(user_id: str, user_filters: dict, chat_summary: str) -> str:
    registry_text = json.dumps(API_REGISTRY, indent=2)
    user_filters_text = json.dumps(user_filters, indent=2)

    prompt = SYSTEM_PROMPT.replace("{api_registry}", registry_text)
    prompt = prompt.replace("{user_filters}", user_filters_text)
    prompt = prompt.replace("{chat_summary}", chat_summary)
    prompt += f"\n\nCurrent user_id: {user_id}"
    return prompt


# ── Main entry point ───────────────────────────────────────────────────

MAX_TOOL_ROUNDS = 5  # safety limit to prevent infinite loops


def run_assistant(
    user_message: str,
    user_id: str,
    db: Session,
    config_db: Session,
) -> dict:
    user_filters = _get_user_filters(config_db, user_id)

    # Load last 5 message pairs (10 rows) from DB and summarize
    recent_messages = _get_recent_messages(config_db, user_id, limit=10)
    chat_summary = _summarize_history(recent_messages)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_prompt = _build_system_prompt(user_id, user_filters, chat_summary)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Tool-calling loop: let the LLM call tools until it produces a final answer
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=FILTER_TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        choice = response.choices[0]

        # If the LLM wants to call tool(s), execute them and feed results back
        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            # Append the assistant message (with tool_calls) to conversation
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                executor = TOOL_EXECUTORS.get(fn_name)

                if executor:
                    try:
                        result = executor(db)
                        tool_result = json.dumps(result)
                    except Exception as e:
                        logger.error(f"Tool {fn_name} failed: {e}")
                        tool_result = json.dumps({"error": str(e)})
                else:
                    tool_result = json.dumps({"error": f"Unknown tool: {fn_name}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

            # Continue the loop — the LLM will now see the tool results
            continue

        # No more tool calls — the LLM produced its final text response
        raw = choice.message.content.strip() if choice.message.content else ""
        break
    else:
        # Exhausted MAX_TOOL_ROUNDS
        raw = json.dumps({
            "message": "I had trouble processing your request. Please try again.",
            "actions": [],
        })

    # Parse the final JSON response
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"message": raw, "actions": []}

    # Ensure message is never empty
    if not result.get("message"):
        result["message"] = "Here is the information you requested."

    # Clean newlines from message — replace \n with spaces for clean UI display
    message = result.get("message", "")
    message = message.replace("\n", " ").replace("  ", " ").strip()

    # Save this exchange to DB
    _save_messages(config_db, user_id, user_message, raw)

    return {
        "message": message,
        "actions": result.get("actions", []),
    }
