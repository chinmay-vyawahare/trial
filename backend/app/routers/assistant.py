"""
AI Assistant endpoints.

POST /api/v1/schedular/assistant/chat?user_id=xxx
  - Takes a user message in body + user_id from query params
  - Chat history is managed in DB per user_id
  - Returns recommended API endpoints + params for the frontend to call

POST /api/v1/schedular/resume
  - Resume a simulation after HITL (human-in-the-loop)
  - Takes thread_id + user's clarification answer
"""

import asyncio
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db, get_config_db
from app.services.assistant.service import run_assistant
from app.services.assistant.nodes.simulation import resume_tool

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular",
    tags=["assistant"],
)


class ChatRequest(BaseModel):
    message: str = Field(default="Give the current filters", description="User message to the assistant")


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., description="Thread ID from the simulation")
    clarification: str = Field(..., description="User's answer to the HITL question")


@router.post("/assistant/chat")
def chat(
    body: ChatRequest,
    user_id: str = Query(..., description="User ID (required)"),
    thread_id: str = Query(..., description="Thread ID for conversation isolation"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    if not thread_id or not thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required and cannot be empty.")

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required and cannot be empty.")

    try:
        return run_assistant(
            user_message=body.message.strip(),
            user_id=user_id.strip(),
            thread_id=thread_id.strip(),
            db=db,
            config_db=config_db,
        )
    except Exception as e:
        logger.exception(f"Assistant error for user '{user_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process your request. Please try again.",
        )


@router.post("/resume")
async def resume_simulation(body: ResumeRequest):
    """
    Resume a simulation after HITL (human-in-the-loop).

    When a simulation returns hitl_required, the frontend collects the user's
    answer and calls this endpoint to resume the simulation stream.
    """
    if not body.thread_id or not body.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required.")
    if not body.clarification or not body.clarification.strip():
        raise HTTPException(status_code=400, detail="clarification is required.")

    try:
        result = await resume_tool(
            thread_id=body.thread_id.strip(),
            answer=body.clarification.strip(),
        )
        return result
    except Exception as e:
        logger.exception(f"Resume error for thread '{body.thread_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to resume simulation. Please try again.",
        )
