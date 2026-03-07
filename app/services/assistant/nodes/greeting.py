"""
Greeting node — handles greetings, small talk, pleasantries.
Returns a friendly response with no actions.
"""

import json
import logging

from app.services.assistant.llm import get_chat_llm

logger = logging.getLogger(__name__)

GREETING_PROMPT = """You are a warm, conversational assistant for Nokia's construction project tracker.

The user has sent a greeting or casual message. Respond naturally like a helpful colleague would.

Guidelines:
- Match the user's energy — if they're casual ("hey!"), be casual back. If formal ("Good morning"), be polished.
- For first-time greetings, briefly mention you can help manage site filters and explore scheduling data.
- For "thank you" / "thanks", respond graciously (e.g. "You're welcome! Let me know if you need anything else.").
- For "bye" / "goodbye", wish them well briefly.
- For small talk ("how are you?"), keep it light and redirect gently to how you can help.
- Do NOT list bullet points of capabilities. Keep it conversational and natural.
- Keep responses to 1-2 sentences max. No walls of text.

Respond with ONLY a JSON object:
{"message": "your friendly response here", "actions": []}

No markdown, no code blocks, just the JSON.
"""


def handle_greeting(user_message: str, chat_summary: str) -> dict:
    """Handle greeting/small talk messages."""
    llm = get_chat_llm(temperature=0.7, max_tokens=200)

    messages = [
        ("system", GREETING_PROMPT),
    ]

    if chat_summary and chat_summary != "No previous conversation.":
        messages.append(("system", f"Recent conversation context:\n{chat_summary}"))

    messages.append(("human", user_message))

    try:
        logger.info("  [GREETING] Generating response ...")
        response = llm.invoke(messages)
        raw = response.content.strip()
        logger.info("  [GREETING] LLM raw: %s", raw[:200])
        result = json.loads(raw)
        if not result.get("message"):
            result["message"] = "Hello! How can I help you with construction scheduling today?"
        result.setdefault("actions", [])
        logger.info("  [GREETING] Response: \"%s\"", result["message"][:150])
        return result
    except Exception as e:
        logger.error("  [GREETING] Failed: %s — using fallback", e)
        return {
            "message": "Hello! How can I help you with construction scheduling today?",
            "actions": [],
        }
