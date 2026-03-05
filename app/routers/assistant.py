"""
AI Assistant endpoint.

POST /api/v1/schedular/assistant/chat?user_id=xxx
  - Takes a user message in body + user_id from query params
  - Chat history is managed in DB per user_id
  - Returns recommended API endpoints + params for the frontend to call
"""

import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db, get_config_db
from app.services.assistant.service import run_assistant

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular/assistant",
    tags=["assistant"],
)


class ChatRequest(BaseModel):
    message: str = Field(default="Give the current filters", description="User message to the assistant")


@router.post("/chat")
def chat(
    body: ChatRequest,
    user_id: str = Query(..., description="User ID (required)"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required and cannot be empty.")

    try:
        return run_assistant(
            user_message=body.message.strip(),
            user_id=user_id.strip(),
            db=db,
            config_db=config_db,
        )
    except Exception as e:
        logger.exception(f"Assistant error for user '{user_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process your request. Please try again.",
        )
