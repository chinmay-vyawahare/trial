"""Minimal Streamlit tester for the assistant's scheduler node.

Run with the backend venv:
    cd /Users/abcom/Desktop/schedular_agent/backend
    ./venv/bin/python -m streamlit run streamlit_assistant.py

Lets you send messages one by one, pick project_type (macro|ahloa), and inspect
the assistant's message + actions. Keeps a short in-memory history per session
so follow-ups like "yes" / "confirm" work.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Stream scheduler/service/planner logs to the terminal running Streamlit.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
    stream=sys.stderr,
    force=True,
)
for _name in (
    "app.services.assistant.nodes.scheduler",
    "app.services.assistant.nodes.planner",
    "app.services.assistant.service",
):
    logging.getLogger(_name).setLevel(logging.INFO)

sys.path.insert(0, str(Path(__file__).parent))

# gpt-5-nano rejects temperature=0; strip it from the raw OpenAI client.
from app.services.assistant import llm as _llm  # noqa: E402
_real_get_openai_client = _llm.get_openai_client


def _patched_client():
    cli = _real_get_openai_client()
    orig_create = cli.chat.completions.create

    def _create(**kwargs):
        kwargs.pop("temperature", None)
        return orig_create(**kwargs)

    cli.chat.completions.create = _create  # type: ignore[assignment]
    return cli


_llm.get_openai_client = _patched_client
from app.services.assistant.nodes import scheduler as _scheduler_mod  # noqa: E402
_scheduler_mod.get_openai_client = _patched_client

import requests  # noqa: E402
import streamlit as st  # noqa: E402
from app.core.database import SessionLocal, ConfigSessionLocal  # noqa: E402
from app.services.assistant.nodes.scheduler import handle_scheduler  # noqa: E402
from app.services.assistant.service import _get_user_filters  # noqa: E402


def _execute_action(base_url: str, action: dict) -> dict:
    """Send an action (as produced by the scheduler) to the running backend."""
    method = (action.get("method") or "GET").upper()
    endpoint = action.get("endpoint") or ""
    params = action.get("params") or {}
    url = base_url.rstrip("/") + endpoint if endpoint.startswith("/") else endpoint

    kwargs: dict = {"timeout": 30}
    if method == "POST":
        kwargs["json"] = params
    elif method in ("GET", "DELETE"):
        # Path/query params are usually already baked into the endpoint string.
        # Any leftover dict params are forwarded as query string.
        kwargs["params"] = {k: v for k, v in params.items() if v is not None}

    resp = requests.request(method, url, **kwargs)
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    return {"status": resp.status_code, "url": url, "method": method, "body": body}


st.set_page_config(page_title="Assistant tester", layout="wide")
st.title("Assistant scheduler tester")

with st.sidebar:
    st.header("Settings")
    project_type = st.selectbox("project_type", ["macro", "ahloa"], index=0)
    user_id = st.text_input("user_id", value="scratch_test_user")
    backend_url = st.text_input("backend base URL", value="http://localhost:8000")

    st.divider()
    st.caption("Current DB filters for this user:")
    try:
        _cdb = ConfigSessionLocal()
        try:
            _current_filters = _get_user_filters(_cdb, user_id)
        finally:
            _cdb.close()
        st.code(json.dumps(_current_filters, indent=2, default=str), language="json")
    except Exception as _e:
        _current_filters = {"status": "No saved filters"}
        st.warning(f"Could not load filters: {_e}")

    if st.button("Clear history"):
        st.session_state.pop("history", None)
        st.session_state.pop("action_results", None)
        st.rerun()

if "action_results" not in st.session_state:
    st.session_state["action_results"] = {}  # { "<turn>-<idx>": {status, url, method, body} }

if "history" not in st.session_state:
    st.session_state["history"] = []  # list of {"role": "user"|"assistant", "content": str, "meta": {...}}


# Render prior turns
for turn_idx, turn in enumerate(st.session_state["history"]):
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn["role"] == "assistant":
            actions = turn.get("meta", {}).get("actions") or []
            if actions:
                st.markdown("**Actions:**")
                for a_idx, a in enumerate(actions):
                    action_key = f"{turn_idx}-{a_idx}"
                    st.code(
                        f"{a.get('method')} {a.get('endpoint')}\n"
                        f"params = {json.dumps(a.get('params', {}), indent=2, default=str)}",
                        language="http",
                    )
                    cols = st.columns([1, 6])
                    with cols[0]:
                        if st.button(
                            f"Call #{a_idx + 1}",
                            key=f"call-{action_key}",
                            help=f"Send this {a.get('method')} to {backend_url}",
                        ):
                            try:
                                st.session_state["action_results"][action_key] = (
                                    _execute_action(backend_url, a)
                                )
                            except Exception as exc:
                                st.session_state["action_results"][action_key] = {
                                    "status": "ERR",
                                    "url": a.get("endpoint"),
                                    "method": a.get("method"),
                                    "body": f"{type(exc).__name__}: {exc}",
                                }
                            st.rerun()
                    res = st.session_state["action_results"].get(action_key)
                    if res is not None:
                        status = res.get("status")
                        ok = isinstance(status, int) and 200 <= status < 300
                        with cols[1]:
                            (st.success if ok else st.error)(
                                f"{res['method']} {res['url']} → {status}"
                            )
                            body = res.get("body")
                            if isinstance(body, (dict, list)):
                                st.code(json.dumps(body, indent=2, default=str), language="json")
                            else:
                                st.code(str(body))
            else:
                st.caption("_(no actions)_")


user_msg = st.chat_input("Ask about filters, prerequisites, skip/unskip, etc.")
if user_msg:
    st.session_state["history"].append({"role": "user", "content": user_msg})

    recent = [
        {"role": t["role"], "content": t["content"]}
        for t in st.session_state["history"][-12:]
    ]
    chat_summary = "\n".join(
        f"- {'User' if t['role'] == 'user' else 'Assistant'}: {t['content'][:300]}"
        for t in recent
    ) or "No previous conversation."

    db = SessionLocal()
    cdb = ConfigSessionLocal()
    try:
        # Always fetch fresh filters from DB for this user (same as production).
        user_filters = _get_user_filters(cdb, user_id)
        with st.spinner(f"Calling scheduler ({project_type}) ..."):
            result = handle_scheduler(
                user_message=user_msg,
                user_id=user_id,
                user_filters=user_filters,
                chat_summary=chat_summary,
                db=db,
                recent_messages=recent[:-1],  # exclude current user message
                config_db=cdb,
                project_type=project_type,
            )
    except Exception as e:
        st.session_state["history"].append({
            "role": "assistant",
            "content": f"_Exception:_ `{type(e).__name__}: {e}`",
            "meta": {"actions": []},
        })
    else:
        st.session_state["history"].append({
            "role": "assistant",
            "content": result.get("message", ""),
            "meta": {"actions": result.get("actions", [])},
        })
    finally:
        db.close()
        cdb.close()
    st.rerun()
