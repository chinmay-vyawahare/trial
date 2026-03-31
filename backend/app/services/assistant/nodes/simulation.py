
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
