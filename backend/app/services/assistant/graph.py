"""
LangGraph-based assistant flow.

Graph structure:
  START → planner → (greeting | scheduler | simulation) → END

The planner classifies intent, then routes to the appropriate handler node.
"""

import logging
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from .nodes.planner import classify_intent
from .nodes.greeting import handle_greeting
from .nodes.scheduler import handle_scheduler
from .nodes.simulation import handle_simulation

logger = logging.getLogger(__name__)


class AssistantState(TypedDict):
    user_message: str
    user_id: str
    thread_id: str
    chat_summary: str
    recent_messages: list[dict]
    user_filters: dict
    db: Session
    config_db: Session
    intent: str
    result: dict


# ── Node functions ─────────────────────────────────────────────────────

def planner_node(state: AssistantState) -> dict:
    """Classify user intent."""
    intent = classify_intent(state["user_message"], state["chat_summary"])
    logger.info(f"Planner classified intent as: {intent}")
    return {"intent": intent}


def greeting_node(state: AssistantState) -> dict:
    """Handle greeting messages."""
    result = handle_greeting(state["user_message"], state["chat_summary"])
    return {"result": result}


def scheduler_node(state: AssistantState) -> dict:
    """Handle scheduler messages with tool calling."""
    result = handle_scheduler(
        user_message=state["user_message"],
        user_id=state["user_id"],
        user_filters=state["user_filters"],
        chat_summary=state["chat_summary"],
        db=state["db"],
        recent_messages=state.get("recent_messages"),
        config_db=state.get("config_db"),
    )
    return {"result": result}


def simulation_node(state: AssistantState) -> dict:
    """Handle simulation messages (placeholder)."""
    result = handle_simulation(state["user_message"], state["chat_summary"])
    return {"result": result}


# ── Router ─────────────────────────────────────────────────────────────

def route_by_intent(state: AssistantState) -> Literal["greeting", "scheduler", "simulation"]:
    """Route to the correct handler based on classified intent."""
    return state["intent"]


# ── Build the graph ────────────────────────────────────────────────────

def build_assistant_graph() -> StateGraph:
    graph = StateGraph(AssistantState)

    graph.add_node("planner", planner_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("scheduler", scheduler_node)
    graph.add_node("simulation", simulation_node)

    graph.set_entry_point("planner")

    graph.add_conditional_edges(
        "planner",
        route_by_intent,
        {
            "greeting": "greeting",
            "scheduler": "scheduler",
            "simulation": "simulation",
        },
    )

    graph.add_edge("greeting", END)
    graph.add_edge("scheduler", END)
    graph.add_edge("simulation", END)

    return graph.compile()


# Compile once at module level
assistant_graph = build_assistant_graph()
