"""
AI Assistant service — ChatOpenAI.

The LLM does NOT execute anything. It returns API endpoint(s) + params
that the frontend should call.

All available filter values (markets, regions, etc.) are loaded from DB
and injected into the system prompt so the LLM can match user input to
real values.

Chat history is persisted per user_id in the chat_history table.
The last 5 message pairs are summarized and included in the system prompt.
"""

import json
import os
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from sqlalchemy import text

from .tools import API_REGISTRY
from app.services.gantt import get_filter_options
from app.models.prerequisite import UserFilter, ChatHistory

_BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)

SYSTEM_PROMPT = """You are a scheduling assistant for Nokia's construction project tracker.

Your job: take the user's natural language request and return the API endpoint
the frontend should call, with the correct query params filled in.

You do NOT execute anything. You only return instructions for the frontend.

## AVAILABLE API ENDPOINTS:

{api_registry}

## AVAILABLE FILTER VALUES (from database):

{filter_values}

## CURRENT USER FILTERS:

{user_filters}

## RECENT CONVERSATION SUMMARY:

{chat_summary}

## RULES:

1. Always respond with a JSON object:
   - "message": short human-readable explanation
   - "actions": list of API calls for the frontend

2. Each action must have:
   - "method": GET
   - "endpoint": full path (replace {{user_id}} with actual value)
   - "params": query params dict (only include non-null values)

3. When user asks to change a filter (e.g. "change market to Dallas"):
   - Return the gantt-charts endpoint with user_id + the changed filter param
   - The backend auto-saves filters when user_id is provided
   - Do NOT return a separate save/update call
   - IMPORTANT: match the user's input to the exact value from AVAILABLE FILTER VALUES
   - If the user's input does NOT exactly match any available filter value but is CLOSE to one or more values (e.g. typo like "southh" for "South", or partial match like "dal" for "Dallas"):
     * Do NOT just say the value is invalid
     * Instead, suggest the closest matching value(s) as a follow-up question
     * Example: if user says "southh" and available regions are ["South", "North", "East", "West"], respond with:
       {{"message": "Did you mean 'South'? Please confirm and I'll update the region filter.", "actions": []}}
     * If multiple values could match (e.g. "new" could match "New York" and "New Jersey"), list all relevant options:
       {{"message": "I found multiple matches. Did you mean one of these?\n1. New York\n2. New Jersey\nPlease specify which one.", "actions": []}}
   - If the user's input does NOT match or resemble ANY available filter value at all, then inform the user it's not valid and list the available options for that filter

4. When user asks "what markets are available" or "list regions" or asks about filter options:
   - Answer directly from AVAILABLE FILTER VALUES above. No need to call an endpoint.
   - Just return the list in the "message" field with empty "actions"

5. When user asks "show dashboard" or "how are things looking":
   - Return the dashboard endpoint with user_id

6. When user asks about constraints or thresholds:
   - Return the constraints endpoint
    
7. Only include params that have actual values. Skip null/empty params.

8. ONLY respond with valid JSON. No markdown, no code blocks.

9. Use the RECENT CONVERSATION SUMMARY to maintain context from prior messages.

10. If user asked for the user's filter return the filters in the message field and do not return an action.
"""


def _get_filter_values(db: Session) -> dict:
    """Fetch all distinct filter values from the staging DB."""
    filters = get_filter_options(db)

    # Gate check values
    plan_types = [
        r[0] for r in db.execute(text(
            f"SELECT DISTINCT por_plan_type FROM public.stg_ndpd_mbt_tmobile_macro_combined "
            f"WHERE {_BASE_WHERE} AND por_plan_type IS NOT NULL ORDER BY por_plan_type"
        ))
    ]
    dev_initiatives = [
        r[0] for r in db.execute(text(
            f"SELECT DISTINCT por_regional_dev_initiatives FROM public.stg_ndpd_mbt_tmobile_macro_combined "
            f"WHERE {_BASE_WHERE} AND por_regional_dev_initiatives IS NOT NULL ORDER BY por_regional_dev_initiatives"
        ))
    ]

    filters["plan_types"] = plan_types
    filters["regional_dev_initiatives"] = dev_initiatives
    return filters


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
    # Reverse to chronological order
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
        # Truncate long assistant responses to keep summary concise
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"- {role}: {content}")

    return "\n".join(lines)


def _save_messages(config_db: Session, user_id: str, user_msg: str, assistant_msg: str):
    """Save user and assistant messages to chat_history table."""
    config_db.add(ChatHistory(user_id=user_id, role="user", content=user_msg))
    config_db.add(ChatHistory(user_id=user_id, role="assistant", content=assistant_msg))
    config_db.commit()


def _build_system_prompt(user_id: str, filter_values: dict, user_filters: dict, chat_summary: str) -> str:
    registry_text = json.dumps(API_REGISTRY, indent=2)
    filters_text = json.dumps(filter_values, indent=2)
    user_filters_text = json.dumps(user_filters, indent=2)

    prompt = SYSTEM_PROMPT.replace("{api_registry}", registry_text)
    prompt = prompt.replace("{filter_values}", filters_text)
    prompt = prompt.replace("{user_filters}", user_filters_text)
    prompt = prompt.replace("{chat_summary}", chat_summary)
    prompt += f"\n\nCurrent user_id: {user_id}"
    return prompt


def run_assistant(
    user_message: str,
    user_id: str,
    db: Session,
    config_db: Session,
) -> dict:
    # Load filter values from DB
    filter_values = _get_filter_values(db)
    user_filters = _get_user_filters(config_db, user_id)

    # Load last 5 message pairs (10 rows) from DB and summarize
    recent_messages = _get_recent_messages(config_db, user_id, limit=10)
    chat_summary = _summarize_history(recent_messages)

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0,
    )

    system_prompt = _build_system_prompt(user_id, filter_values, user_filters, chat_summary)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"message": raw, "actions": []}

    # Save this exchange to DB
    _save_messages(config_db, user_id, user_message, raw)

    return {
        "message": result.get("message", ""),
        "actions": result.get("actions", []),
    }
