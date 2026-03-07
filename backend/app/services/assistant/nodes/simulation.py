"""
Simulation node — calls the external simulation agent via SSE.

Two tools:
  simulate_tool  — starts the SSE stream; returns when complete OR when HITL fires
  resume_tool    — called after HITL with the same thread_id + user's answer

The external simulation agent base URL is configured via SIMULATION_BASE_URL.
When HITL is required, the node returns a response with status="hitl_required"
and the frontend calls POST /schedular/resume to continue.
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
_result_queues: dict[str, asyncio.Queue] = {}
_resume_events: dict[str, asyncio.Event] = {}


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

    If "hitl_required" is returned, the frontend should call POST /schedular/resume.
    """
    tid = thread_id or str(uuid.uuid4())
    result_queue: asyncio.Queue = asyncio.Queue()

    async def _stream_task():
        nonlocal tid
        event_name = None

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

                            elif event_name == "hitl_start":
                                resume_event = asyncio.Event()
                                _resume_events[tid] = resume_event
                                _result_queues[tid] = result_queue

                                await result_queue.put(("hitl", data, tid))

                                # Block — SSE connection stays open until resume
                                await resume_event.wait()

                            elif event_name == "complete":
                                await result_queue.put(("complete", data.get("final_response", ""), tid))
                                break

                            elif event_name == "error":
                                await result_queue.put(("error", data.get("message", "Unknown error"), tid))
                                break

        except httpx.ConnectError:
            await result_queue.put(("error", "Could not connect to simulation agent", tid))
        except Exception as e:
            logger.exception(f"Simulation stream error: {e}")
            await result_queue.put(("error", str(e), tid))

    asyncio.create_task(_stream_task())

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

    Unblocks the background SSE task, signals the external agent,
    and waits for the stream to deliver the final response.

    Returns:
      {"status": "complete", "thread_id": str, "final_response": str}
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

    # Unblock the background SSE task
    resume_event.set()

    # Signal the external agent to resume
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{SIMULATION_BASE_URL}/simulate/stream/resume",
            json={"thread_id": thread_id, "clarification": clarification},
        )
        r.raise_for_status()

    # Wait for the background task to deliver the final result
    event_type, data, tid = await result_queue.get()

    # Cleanup
    _resume_events.pop(thread_id, None)
    _result_queues.pop(thread_id, None)

    if event_type == "complete":
        return {"status": "complete", "thread_id": tid, "final_response": data}
    else:
        return {"status": "error", "thread_id": tid, "message": data}


def handle_simulation(user_message: str, chat_summary: str) -> dict:
    """
    Synchronous entry point for the simulation node in the LangGraph flow.

    Starts the simulation via the async simulate_tool. If HITL is required,
    returns the clarification questions so the frontend can call /resume.
    """
    logger.info("  [SIMULATION] Starting simulation for query: %s", user_message[:100])

    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(
                asyncio.run,
                simulate_tool(query=user_message, user_id="system", thread_id=None),
            ).result()
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
