"""
Planner node — classifies user intent into one of:
  greeting, scheduler, simulation
"""

import json
import logging

from app.services.assistant.llm import get_chat_llm, LLM_MODEL

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """You are an intent classifier for Nokia's construction project tracker assistant.

Given a user message, classify it into EXACTLY ONE of these intents:

1. "greeting" — greetings, small talk, thank you, goodbye, how are you, pleasantries,
   or any casual/non-work message that doesn't relate to filters or simulation.

2. "scheduler" — anything related to viewing or changing FILTERS or PREREQUISITES,
   or asking about the user's AI Excel upload data:
   - Setting/changing/clearing filters (region, market, area, vendor, site, plan type, dev initiatives)
   - Asking what filter values are available ("list markets", "what regions exist?")
   - Asking about the user's current/saved filters
   - Any request to update or get filter-related data
   - Removing/disabling prerequisite milestones ("remove steel received", "disable NTP")
   - Skipping/Unskipping prerequisite milestones ("skip steel received", "unskip NTP")
   - Adding/enabling previously removed prerequisite milestones ("add NTP", "enable steel received")
   - Asking which prerequisites/milestones are removed or disabled
   - Listing available prerequisites or milestones
   - Asking about the AI Excel upload / uploaded notes / extracted CX dates
     ("what did I upload", "show my uploaded sites", "which sites are blocked",
      "what is the CX for site X", "list blocked sites with reasons",
      "summarize my Excel upload", "what notes did I upload")

3. "simulation" — anything else work-related that is NOT about filters or prerequisites:
   - What-if scenarios, simulating changes
   - Dashboard, status, milestones
   - Constraints, thresholds, SLA
   - Exporting data, gate checks
   - Construction progress, forecasts
   - Backward planning, impact analysis

IMPORTANT: If the recent conversation context shows the assistant asked a follow-up question
(e.g. "Did you mean X?", "Would you like to proceed?", "Are you sure?") and the user is
confirming or responding to that question (e.g. "yes", "no", "go ahead", "sure", "confirm"),
then classify with the SAME intent as the original question — NOT as "greeting".

Respond with ONLY a JSON object: {"intent": "greeting" | "scheduler" | "simulation"}

No explanation, no markdown, just the JSON.
"""


def classify_intent(user_message: str, chat_summary: str) -> str:
    """Classify user message intent. Returns 'greeting', 'scheduler', or 'simulation'."""
    llm = get_chat_llm(temperature=0, max_tokens=50)

    messages = [
        ("system", PLANNER_PROMPT),
    ]

    if chat_summary and chat_summary != "No previous conversation.":
        messages.append(("system", f"Recent conversation context:\n{chat_summary}"))

    messages.append(("human", user_message))

    try:
        logger.info(
            "\n"
            "  [PLANNER] Classifying intent ...\n"
            "  [PLANNER] Model: %s\n"
            "  [PLANNER] Input: \"%s\"",
            LLM_MODEL, user_message[:100],
        )
        response = llm.invoke(messages)
        raw = response.content.strip()
        result = json.loads(raw)
        intent = result.get("intent", "scheduler")
        if intent not in ("greeting", "scheduler", "simulation"):
            intent = "scheduler"
        logger.info("  [PLANNER] Intent => %s", intent)
        return intent
    except Exception as e:
        logger.error("  [PLANNER] Classification failed: %s — defaulting to 'scheduler'", e)
        return "scheduler"
