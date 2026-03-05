"""
AI Assistant endpoint.

POST /api/v1/schedular/assistant/chat?user_id=xxx
  - Takes a user message in body + user_id from query params
  - Chat history is managed in DB per user_id
  - Returns recommended API endpoints + params for the frontend to call
"""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db, get_config_db
from app.services.assistant.service import run_assistant

router = APIRouter(
    prefix="/api/v1/schedular/assistant",
    tags=["assistant"],
)


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(
    body: ChatRequest,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    config_db: Session = Depends(get_config_db),
):
    return run_assistant(
        user_message=body.message,
        user_id=user_id,
        db=db,
        config_db=config_db,
    )
