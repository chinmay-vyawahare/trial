"""
AI Assistant service — LangGraph-based with intent routing.

Flow: planner → (greeting | scheduler | simulation)

The planner classifies intent, then routes to the appropriate handler.
Scheduler node uses OpenAI tool-calling to return API endpoints for the frontend.

Chat history is persisted per user_id + thread_id in the chat_history table.
The last 5 message pairs (10 rows) are summarized and included in the system prompt
so the LLM has enough context for follow-up confirmations.
"""

import json
import logging
from sqlalchemy.orm import Session

from app.models.prerequisite import UserFilter, ChatHistory
from .graph import assistant_graph

logger = logging.getLogger(__name__)


# ── DB helpers ─────────────────────────────────────────────────────────

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


def _get_recent_messages(config_db: Session, user_id: str, thread_id: str, limit: int = 10) -> list[dict]:
    """Load last N messages from chat_history table filtered by thread_id.

    Default limit=10 (5 user + assistant pairs) so the LLM has enough
    conversational context for follow-ups like "yes" / "confirm".
    """
    rows = (
        config_db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id, ChatHistory.thread_id == thread_id)
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


def _save_messages(config_db: Session, user_id: str, thread_id: str, user_msg: str, assistant_msg: str):
    """Save user and assistant messages to chat_history table for a specific thread."""
    config_db.add(ChatHistory(user_id=user_id, thread_id=thread_id, role="user", content=user_msg))
    config_db.add(ChatHistory(user_id=user_id, thread_id=thread_id, role="assistant", content=assistant_msg))
    config_db.commit()


# ── Main entry point ───────────────────────────────────────────────────

def run_assistant(
    user_message: str,
    user_id: str,
    thread_id: str,
    db: Session,
    config_db: Session,
) -> dict:
    logger.info(
        "\n"
        "==============================================================\n"
        "  ASSISTANT REQUEST\n"
        "==============================================================\n"
        "  User ID   : %s\n"
        "  Thread ID : %s\n"
        "  Message   : %s\n"
        "==============================================================",
        user_id, thread_id, user_message,
    )

    user_filters = _get_user_filters(config_db, user_id)
    logger.info("  Loaded user filters: %s", json.dumps(user_filters, default=str))

    # Load last 5 message pairs (10 rows) from DB for this thread and summarize
    recent_messages = _get_recent_messages(config_db, user_id, thread_id)
    chat_summary = _summarize_history(recent_messages)
    logger.info("  Chat history : %d messages loaded", len(recent_messages))

    # Run the LangGraph flow: planner → (greeting | scheduler | simulation)
    logger.info("  Starting LangGraph flow ...")
    state = assistant_graph.invoke({
        "user_message": user_message,
        "user_id": user_id,
        "thread_id": thread_id,
        "chat_summary": chat_summary,
        "user_filters": user_filters,
        "db": db,
        "config_db": config_db,
        "intent": "",
        "result": {},
    })

    result = state["result"]

    # Ensure message is never empty
    if not result.get("message"):
        result["message"] = "Here is the information you requested."

    # Clean newlines from message for clean UI display
    message = result.get("message", "")
    message = message.replace("\n", " ").replace("  ", " ").strip()

    # Save this exchange to DB — store only the human-readable message,
    # not the full JSON with actions, so the chat summary stays clean
    _save_messages(config_db, user_id, thread_id, user_message, message)

    logger.info(
        "\n"
        "--------------------------------------------------------------\n"
        "  ASSISTANT RESPONSE\n"
        "--------------------------------------------------------------\n"
        "  Intent  : %s\n"
        "  Message : %s\n"
        "  Actions : %d action(s)\n"
        "==============================================================",
        state.get("intent", "?"), message, len(result.get("actions", [])),
    )

    return {
        "message": message,
        "actions": result.get("actions", []),
    }
