# Route

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
import json
import logging
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func, distinct

from app.core.database import get_db, get_config_db, ConfigSessionLocal
from app.models.prerequisite import ChatHistory
from app.schemas.gantt import ChatMessageOut, ChatThreadSummary, ChatThreadOut, ChatHistoryOut
from app.services.assistant.service import run_assistant
from app.services.assistant.nodes.simulation import resume_tool_stream, simulate_tool_stream
from app.services.assistant.nodes.planner import classify_intent
from app.services.assistant.service import _get_recent_messages, _summarize_history, _save_messages

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedular",
    tags=["assistant"],
)


class ChatRequest(BaseModel):
    message: str = Field(default="Give the current filters", description="User message to the assistant")


class CreateThreadRequest(BaseModel):
    user_id: str = Field(..., description="User ID to create the thread for")


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., description="Thread ID from the simulation")
    chat_thread_id: str = Field(..., description="Chat thread ID to save response to")
    user_id: str = Field(..., description="User ID for chat history")
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

    user_id = user_id.strip()
    thread_id = thread_id.strip()
    message = body.message.strip()

    # Classify intent first — if simulation, stream SSE events directly
    recent_messages = _get_recent_messages(config_db, user_id, thread_id)
    chat_summary = _summarize_history(recent_messages)
    intent = classify_intent(message, chat_summary)

    if intent == "simulation":
        # Save user message to chat history
        _save_messages(config_db, user_id, thread_id, message, "")

        async def _stream_and_save():
            final_msg = ""
            async for chunk in simulate_tool_stream(query=message, user_id=user_id, thread_id=None):
                yield chunk
                # Capture final response for chat history
                if "event: complete" in chunk:
                    try:
                        data_line = chunk.split("data: ", 1)[1].strip()
                        parsed = json.loads(data_line)
                        final_msg = parsed.get("final_response", "")
                    except (json.JSONDecodeError, IndexError):
                        pass

            # Save assistant response to chat history
            if final_msg:
                db_session = ConfigSessionLocal()
                try:
                    db_session.add(ChatHistory(
                        user_id=user_id, thread_id=thread_id,
                        role="assistant", content=final_msg,
                    ))
                    db_session.commit()
                finally:
                    db_session.close()

        return StreamingResponse(_stream_and_save(), media_type="text/event-stream")

    # Non-simulation: use the regular sync flow
    try:
        return run_assistant(
            user_message=message,
            user_id=user_id,
            thread_id=thread_id,
            db=db,
            config_db=config_db,
        )
    except Exception as e:
        logger.exception(f"Assistant error for user '{user_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process your request. Please try again.",
        )


@router.post("/assistant/threads")
def create_thread(
    body: CreateThreadRequest,
    config_db: Session = Depends(get_config_db),
):
    """Create a new chat thread for a user. Persists an initial record so it appears in history."""
    if not body.user_id or not body.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required and cannot be empty.")

    user_id = body.user_id.strip()
    thread_id = str(uuid.uuid4())

    # Seed the thread with an initial assistant message so it shows up in history
    config_db.add(ChatHistory(
        user_id=user_id,
        thread_id=thread_id,
        role="assistant",
        content='{"message": "New conversation started. How can I help you?", "actions": []}',
    ))
    config_db.commit()

    return {"thread_id": thread_id, "user_id": user_id}


@router.post("/resume")
async def resume_simulation(body: ResumeRequest):
    """
    Resume a simulation after HITL (human-in-the-loop).

    Streams all SSE events from the external simulation agent to the frontend.
    Saves the final response to the chat thread history.
    """
    if not body.thread_id or not body.thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required.")
    if not body.clarification or not body.clarification.strip():
        raise HTTPException(status_code=400, detail="clarification is required.")

    sim_thread_id = body.thread_id.strip()
    chat_thread_id = body.chat_thread_id.strip()
    uid = body.user_id.strip()
    clarification = body.clarification.strip()

    async def _stream_and_save():
        final_msg = ""
        async for chunk in resume_tool_stream(thread_id=sim_thread_id, answer=clarification):
            yield chunk
            # Capture final response for chat history
            if "event: complete" in chunk:
                try:
                    data_line = chunk.split("data: ", 1)[1].strip()
                    parsed = json.loads(data_line)
                    final_msg = parsed.get("final_response", "")
                except (json.JSONDecodeError, IndexError):
                    pass

        # Save clarification + response to chat thread history
        if chat_thread_id and uid:
            db_session = ConfigSessionLocal()
            try:
                db_session.add(ChatHistory(
                    user_id=uid, thread_id=chat_thread_id,
                    role="user", content=clarification,
                ))
                if final_msg:
                    db_session.add(ChatHistory(
                        user_id=uid, thread_id=chat_thread_id,
                        role="assistant", content=final_msg,
                    ))
                db_session.commit()
            finally:
                db_session.close()

    return StreamingResponse(_stream_and_save(), media_type="text/event-stream")


@router.get("/assistant/history", response_model=list[ChatHistoryOut])
def get_all_chat_history(
    config_db: Session = Depends(get_config_db),
):
    """Get all chat history grouped by user_id and thread_id (all users)."""
    user_ids = [
        r[0] for r in config_db.query(distinct(ChatHistory.user_id)).all()
    ]

    result = []
    for uid in sorted(user_ids):
        threads = _build_threads_for_user(config_db, uid)
        if threads:
            result.append(ChatHistoryOut(user_id=uid, threads=threads))

    return result


@router.get("/assistant/history/{user_id}/threads", response_model=list[ChatThreadSummary])
def get_user_threads(
    user_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Get all thread summaries for a specific user (lightweight, no full messages)."""
    thread_ids = [
        r[0]
        for r in config_db.query(distinct(ChatHistory.thread_id))
        .filter(ChatHistory.user_id == user_id)
        .all()
    ]

    summaries = []
    for tid in thread_ids:
        messages = (
            config_db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.thread_id == tid)
            .order_by(ChatHistory.id.asc())
            .all()
        )
        if not messages:
            continue

        first_user = next((m for m in messages if m.role == "user"), None)
        user_preview = None
        if first_user:
            user_preview = first_user.content[:100] + ("..." if len(first_user.content) > 100 else "")

        first_assistant = next((m for m in messages if m.role == "assistant"), None)
        assistant_preview = None
        if first_assistant:
            content = first_assistant.content
            # Assistant messages are stored as JSON — extract the message field
            try:
                parsed = json.loads(content)
                content = parsed.get("message", content)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
            assistant_preview = content[:120] + ("..." if len(content) > 120 else "")

        summaries.append(ChatThreadSummary(
            thread_id=tid,
            message_count=len(messages),
            first_user_message=user_preview,
            first_assistant_message=assistant_preview,
            last_message_at=messages[-1].created_at,
        ))

    summaries.sort(key=lambda t: t.last_message_at or "", reverse=True)
    return summaries


@router.get("/assistant/history/{user_id}/threads/{thread_id}", response_model=ChatThreadOut)
def get_thread_messages(
    user_id: str,
    thread_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Get full chat messages for a specific user + thread."""
    messages = (
        config_db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id, ChatHistory.thread_id == thread_id)
        .order_by(ChatHistory.id.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=404, detail=f"No messages found for user '{user_id}' thread '{thread_id}'")

    return ChatThreadOut(
        thread_id=thread_id,
        messages=[
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
        last_message_at=messages[-1].created_at,
    )


@router.delete("/assistant/history/{user_id}")
def delete_user_history(
    user_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Delete all chat history for a specific user (all threads)."""
    deleted = (
        config_db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id)
        .delete()
    )
    config_db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No chat history found for user '{user_id}'")
    return {"detail": f"Deleted {deleted} messages for user '{user_id}'"}


@router.delete("/assistant/history/{user_id}/threads/{thread_id}")
def delete_thread(
    user_id: str,
    thread_id: str,
    config_db: Session = Depends(get_config_db),
):
    """Delete all messages for a specific user + thread."""
    deleted = (
        config_db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id, ChatHistory.thread_id == thread_id)
        .delete()
    )
    config_db.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No messages found for user '{user_id}' thread '{thread_id}'")
    return {"detail": f"Deleted {deleted} messages from thread '{thread_id}'"}


def _build_threads_for_user(config_db: Session, user_id: str) -> list[ChatThreadOut]:
    """Helper: build full thread list for a user."""
    thread_ids = [
        r[0]
        for r in config_db.query(distinct(ChatHistory.thread_id))
        .filter(ChatHistory.user_id == user_id)
        .all()
    ]

    threads = []
    for tid in thread_ids:
        messages = (
            config_db.query(ChatHistory)
            .filter(ChatHistory.user_id == user_id, ChatHistory.thread_id == tid)
            .order_by(ChatHistory.id.asc())
            .all()
        )
        if not messages:
            continue
        threads.append(ChatThreadOut(
            thread_id=tid,
            messages=[
                ChatMessageOut(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                )
                for m in messages
            ],
            last_message_at=messages[-1].created_at,
        ))

    threads.sort(key=lambda t: t.last_message_at or "", reverse=True)
    return threads


