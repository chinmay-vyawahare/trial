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
async def chat(
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




# Servise

"""
Simulation node — calls the external simulation agent via SSE.

Tools:
  simulate_tool        — starts SSE stream; returns when complete OR when HITL fires
  simulate_tool_stream — async generator that yields ALL SSE events to the frontend
  resume_tool          — called after HITL; returns final result
  resume_tool_stream   — async generator that yields ALL SSE events after HITL resume

The external simulation agent base URL is configured via SIMULATION_BASE_URL.
When HITL is required, the node returns a response with status="hitl_required"
and the frontend calls POST /schedular/resume to continue.

IMPORTANT: The background SSE task must live on FastAPI's main event loop so that
it survives between the initial /chat call and the later /resume call.  The sync
`handle_simulation()` (called from the synchronous LangGraph graph) schedules work
onto that loop via `asyncio.run_coroutine_threadsafe`, keeping the background task
alive while the sync thread blocks on a `threading.Event`.
"""

import asyncio
import json
import logging
import uuid

import httpx

logger = logging.getLogger(__name__)

# ── External simulation agent base URL (change this later) ────────────
SIMULATION_BASE_URL = "http://localhost:9000"

# ── In-memory HITL state ──────────────────────────────────────────────
# These live on FastAPI's event loop and are shared between simulate_tool
# (background task) and resume_tool (async /resume endpoint).
_result_queues: dict[str, asyncio.Queue] = {}
_resume_events: dict[str, asyncio.Event] = {}

# ── Reference to FastAPI's running event loop ─────────────────────────
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at startup to capture FastAPI's event loop."""
    global _main_loop
    _main_loop = loop


def _get_main_loop() -> asyncio.AbstractEventLoop:
    """Return the main event loop, auto-detecting if not set explicitly."""
    global _main_loop
    if _main_loop is not None:
        return _main_loop
    try:
        loop = asyncio.get_running_loop()
        _main_loop = loop
        return loop
    except RuntimeError:
        raise RuntimeError(
            "No running event loop found. Ensure set_main_loop() is called "
            "at application startup or that this code runs within an async context."
        )


async def _run_stream_task(
    query: str,
    user_id: str,
    tid: str,
    result_queue: asyncio.Queue,
    forward_all: bool = False,
):
    """
    Background task that reads SSE events from the external simulation agent.

    When forward_all=True, ALL events are put on the queue (for streaming to frontend).
    When forward_all=False, only hitl/complete/error are put on the queue (original behavior).
    """
    event_name = None
    resumed = False

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{SIMULATION_BASE_URL}/simulate/stream",
                params={"query": query, "user_id": user_id, "thread_id": tid},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue

                    if line.startswith("event:"):
                        event_name = line[6:].strip()

                    elif line.startswith("data:") and event_name:
                        data = json.loads(line[5:].strip())
                        logger.info("  [SIMULATION] SSE event: %s", event_name)

                        if event_name == "stream_started":
                            tid = data.get("thread_id", tid)
                            if forward_all:
                                await result_queue.put((event_name, data, tid))

                        elif event_name == "hitl_start":
                            resume_event = asyncio.Event()
                            _resume_events[tid] = resume_event
                            _result_queues[tid] = result_queue

                            await result_queue.put(("hitl", data, tid))

                            # Block — SSE connection stays open until resume
                            await resume_event.wait()
                            resumed = True

                        elif event_name == "complete":
                            await result_queue.put(("complete", data.get("final_response", ""), tid))
                            break

                        elif event_name == "error":
                            await result_queue.put(("error", data.get("message", "Unknown error"), tid))
                            break

                        else:
                            # Forward all other events (step, progress, token, etc.)
                            if forward_all or resumed:
                                await result_queue.put((event_name, data, tid))

    except httpx.ConnectError:
        await result_queue.put(("error", "Could not connect to simulation agent", tid))
    except Exception as e:
        logger.exception(f"Simulation stream error: {e}")
        await result_queue.put(("error", str(e), tid))


# ── Original non-streaming tools (kept for backward compat) ──────────


async def simulate_tool(
    query: str,
    user_id: str,
    thread_id: str = None,
) -> dict:
    """
    Start a simulation stream by connecting to the external simulation agent.

    Returns one of:
      {"status": "complete",       "thread_id": str, "final_response": str}
      {"status": "hitl_required",  "thread_id": str, "clarification": dict}
    """
    tid = thread_id or str(uuid.uuid4())
    result_queue: asyncio.Queue = asyncio.Queue()

    asyncio.create_task(_run_stream_task(query, user_id, tid, result_queue, forward_all=False))

    event_type, data, tid = await result_queue.get()

    if event_type == "hitl":
        return {"status": "hitl_required", "thread_id": tid, "clarification": data}
    elif event_type == "complete":
        return {"status": "complete", "thread_id": tid, "final_response": data}
    else:
        return {"status": "error", "thread_id": tid, "message": data}


async def resume_tool(thread_id: str, answer: str) -> dict:
    """
    Resume a simulation that returned status="hitl_required".
    Returns the final result (non-streaming).
    """
    resume_event = _resume_events.get(thread_id)
    result_queue = _result_queues.get(thread_id)

    if resume_event is None or result_queue is None:
        return {
            "status": "error",
            "thread_id": thread_id,
            "message": f"No active HITL session for thread_id='{thread_id}'",
        }

    clarification = answer.strip() or "Accept stated assumptions"

    resume_event.set()

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{SIMULATION_BASE_URL}/simulate/stream/resume",
            json={"thread_id": thread_id, "clarification": clarification},
        )
        r.raise_for_status()

    event_type, data, tid = await result_queue.get()

    _resume_events.pop(thread_id, None)
    _result_queues.pop(thread_id, None)

    if event_type == "complete":
        return {"status": "complete", "thread_id": tid, "final_response": data}
    else:
        return {"status": "error", "thread_id": tid, "message": data}


# ── Streaming generators (yield SSE events to frontend) ──────────────


async def simulate_tool_stream(
    query: str,
    user_id: str,
    thread_id: str = None,
):
    """
    Async generator that starts a simulation and yields ALL SSE events.

    Yields SSE-formatted strings: "event: <name>\ndata: <json>\n\n"
    Stops after 'complete', 'error', or 'hitl' event.
    """
    tid = thread_id or str(uuid.uuid4())
    result_queue: asyncio.Queue = asyncio.Queue()

    asyncio.create_task(_run_stream_task(query, user_id, tid, result_queue, forward_all=True))

    while True:
        event_type, data, tid = await result_queue.get()

        if event_type == "hitl":
            payload = {"status": "hitl_required", "thread_id": tid, "clarification": data}
            yield f"event: hitl_required\ndata: {json.dumps(payload)}\n\n"
            break
        elif event_type == "complete":
            payload = {"status": "complete", "thread_id": tid, "final_response": data}
            yield f"event: complete\ndata: {json.dumps(payload)}\n\n"
            break
        elif event_type == "error":
            payload = {"status": "error", "thread_id": tid, "message": data}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"
            break
        else:
            # Forward intermediate events (step, progress, token, stream_started, etc.)
            payload = {"event": event_type, "thread_id": tid, "data": data}
            yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def resume_tool_stream(thread_id: str, answer: str):
    """
    Async generator that resumes a HITL simulation and yields ALL SSE events.

    Yields SSE-formatted strings until 'complete' or 'error'.
    """
    resume_event = _resume_events.get(thread_id)
    result_queue = _result_queues.get(thread_id)

    if resume_event is None or result_queue is None:
        payload = {
            "status": "error",
            "thread_id": thread_id,
            "message": f"No active HITL session for thread_id='{thread_id}'",
        }
        yield f"event: error\ndata: {json.dumps(payload)}\n\n"
        return

    clarification = answer.strip() or "Accept stated assumptions"

    # Unblock the background SSE task
    resume_event.set()

    # Signal the external agent to resume
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{SIMULATION_BASE_URL}/simulate/stream/resume",
            json={"thread_id": thread_id, "clarification": clarification},
        )
        r.raise_for_status()

    # Yield all events from the queue until complete/error
    while True:
        event_type, data, tid = await result_queue.get()

        if event_type == "complete":
            payload = {"status": "complete", "thread_id": tid, "final_response": data}
            yield f"event: complete\ndata: {json.dumps(payload)}\n\n"
            # Cleanup
            _resume_events.pop(thread_id, None)
            _result_queues.pop(thread_id, None)
            break
        elif event_type == "error":
            payload = {"status": "error", "thread_id": tid, "message": data}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"
            _resume_events.pop(thread_id, None)
            _result_queues.pop(thread_id, None)
            break
        elif event_type == "hitl":
            # Another HITL in the same stream — forward it
            payload = {"status": "hitl_required", "thread_id": tid, "clarification": data}
            yield f"event: hitl_required\ndata: {json.dumps(payload)}\n\n"
            break
        else:
            # Forward intermediate events
            payload = {"event": event_type, "thread_id": tid, "data": data}
            yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


# ── Sync entry point for LangGraph ───────────────────────────────────


def handle_simulation(user_message: str, chat_summary: str) -> dict:
    """
    Synchronous entry point for the simulation node in the LangGraph flow.

    Schedules the async simulate_tool onto FastAPI's main event loop using
    run_coroutine_threadsafe, so the background SSE task stays alive on that
    loop even after this function returns.  The sync thread blocks on a
    threading.Event until the first result (complete or hitl_required) arrives.
    """
    logger.info("  [SIMULATION] Starting simulation for query: %s", user_message[:100])

    try:
        loop = _get_main_loop()
    except RuntimeError as e:
        logger.exception(f"Cannot access main event loop: {e}")
        return {
            "message": "Simulation service is not ready. Please try again.",
            "actions": [],
        }

    try:
        future = asyncio.run_coroutine_threadsafe(
            simulate_tool(query=user_message, user_id="system", thread_id=None),
            loop,
        )
        result = future.result(timeout=120)
    except TimeoutError:
        logger.error("Simulation timed out after 120s")
        return {
            "message": "Simulation timed out. Please try again.",
            "actions": [],
        }
    except Exception as e:
        logger.exception(f"Simulation failed: {e}")
        return {
            "message": f"Simulation encountered an error: {str(e)}",
            "actions": [],
        }

    if result["status"] == "complete":
        return {
            "message": result["final_response"],
            "actions": [],
        }
    elif result["status"] == "hitl_required":
        return {
            "message": "The simulation needs more information before proceeding.",
            "actions": [],
            "hitl_required": True,
            "thread_id": result["thread_id"],
            "clarification": result["clarification"],
        }
    else:
        return {
            "message": result.get("message", "Simulation failed."),
            "actions": [],
        }
