"""
Scheduler API Tester — a friendlier Swagger.

Fetches the endpoint catalog live from FastAPI's /openapi.json — nothing is
hardcoded. If you add/remove routes or change params, just hit "Reload schema".

Run:
    pip install streamlit requests
    streamlit run api_tester/app.py
"""
from __future__ import annotations

import html as _html
import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import requests
import streamlit as st
import streamlit.components.v1 as components


# ---------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------
st.set_page_config(
    page_title="Scheduler API Tester",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main > div { padding-top: 1rem; }
    .method-badge {
        display: inline-block; padding: 3px 10px; border-radius: 6px;
        font-weight: 700; font-size: 0.75rem; color: white; font-family: monospace;
        margin-right: 8px; letter-spacing: 0.5px;
    }
    .m-GET    { background: #22c55e; }
    .m-POST   { background: #3b82f6; }
    .m-PUT    { background: #f59e0b; }
    .m-PATCH  { background: #a855f7; }
    .m-DELETE { background: #ef4444; }
    .path-text { font-family: 'SF Mono', Menlo, monospace; color: #d4d4d4; }
    .status-ok    { color: #22c55e; font-weight: 700; }
    .status-warn  { color: #f59e0b; font-weight: 700; }
    .status-err   { color: #ef4444; font-weight: 700; }
    div[data-testid="stSidebar"] { width: 360px !important; }
    .summary-box {
        background: rgba(255,255,255,0.03); border-left: 3px solid #3b82f6;
        padding: 10px 14px; margin: 8px 0 18px 0; border-radius: 4px;
        color: #cbd5e1; font-size: 0.9rem;
    }
    .resp-scroll {
        display: block; width: 100%; box-sizing: border-box;
        max-height: 500px; overflow-y: auto; overflow-x: auto;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 8px; padding: 14px 16px;
        background: #0d1117;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        margin: 0;
    }
    .resp-scroll pre {
        margin: 0; padding: 0;
        white-space: pre;
        font-family: 'SF Mono', Menlo, Consolas, monospace;
        font-size: 0.82rem; line-height: 1.55;
        tab-size: 2;
    }
    .resp-scroll pre, .resp-scroll pre * {
        font-variant-ligatures: none;
    }
    /* JSON syntax colors (tokyo-night-ish) */
    .j-key    { color: #7dd3fc; }          /* light blue */
    .j-str    { color: #a3e635; }          /* lime */
    .j-num    { color: #fbbf24; }          /* amber */
    .j-bool   { color: #f472b6; font-weight: 600; }  /* pink */
    .j-null   { color: #94a3b8; font-style: italic; }
    .j-punct  { color: #64748b; }
    .resp-scroll::-webkit-scrollbar { width: 10px; height: 10px; }
    .resp-scroll::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.15); border-radius: 5px;
    }
    .resp-scroll::-webkit-scrollbar-thumb:hover {
        background: rgba(255,255,255,0.25);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------
# Session defaults
# ---------------------------------------------------------------
def _init():
    ss = st.session_state
    ss.setdefault("base_url", "http://localhost:8000")
    ss.setdefault("selected_key", None)
    ss.setdefault("history", [])
    ss.setdefault("last_response", None)
    ss.setdefault("filter_text", "")
    ss.setdefault("method_filter", "ALL")
    ss.setdefault("schema", None)
    ss.setdefault("schema_error", None)


_init()


METHOD_COLORS = {
    "GET": "m-GET", "POST": "m-POST", "PUT": "m-PUT",
    "PATCH": "m-PATCH", "DELETE": "m-DELETE",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def method_badge(method: str) -> str:
    return f'<span class="method-badge {METHOD_COLORS.get(method, "m-GET")}">{method}</span>'


_JSON_TOKEN = re.compile(
    r'("(?:\\.|[^"\\])*"\s*:)'                    # 1: key with trailing colon
    r'|("(?:\\.|[^"\\])*")'                        # 2: string
    r'|\b(true|false)\b'                           # 3: bool
    r'|\b(null)\b'                                 # 4: null
    r'|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'         # 5: number
    r'|([{}\[\],])'                                # 6: punctuation
)


def render_code_html(inner_html: str, height: int = 520) -> None:
    """Render syntax-highlighted code in a scrollable iframe (preserves \\n)."""
    doc = f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
      html, body {{ margin:0; padding:0; background:#0d1117; }}
      body {{ font-family: 'SF Mono', Menlo, Consolas, monospace; color:#e5e7eb; }}
      .wrap {{
        max-height: 500px; overflow:auto;
        border:1px solid rgba(255,255,255,0.10); border-radius:8px;
        padding:14px 16px; background:#0d1117;
      }}
      pre {{
        margin:0; padding:0; white-space:pre;
        font-family:'SF Mono', Menlo, Consolas, monospace;
        font-size:12.5px; line-height:1.55; tab-size:2;
      }}
      .j-key   {{ color:#7dd3fc; }}
      .j-str   {{ color:#a3e635; }}
      .j-num   {{ color:#fbbf24; }}
      .j-bool  {{ color:#f472b6; font-weight:600; }}
      .j-null  {{ color:#94a3b8; font-style:italic; }}
      .j-punct {{ color:#64748b; }}
      .wrap::-webkit-scrollbar {{ width:10px; height:10px; }}
      .wrap::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,0.15); border-radius:5px; }}
      .wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(255,255,255,0.25); }}
    </style></head><body>
      <div class="wrap"><pre>{inner_html}</pre></div>
    </body></html>
    """
    components.html(doc, height=height, scrolling=False)


def highlight_json(text: str) -> str:
    def repl(m: re.Match) -> str:
        k, s, b, n, num, p = m.groups()
        if k is not None:  # "key":
            return f'<span class="j-key">{_html.escape(k)}</span>'
        if s is not None:
            return f'<span class="j-str">{_html.escape(s)}</span>'
        if b is not None:
            return f'<span class="j-bool">{b}</span>'
        if n is not None:
            return f'<span class="j-null">{n}</span>'
        if num is not None:
            return f'<span class="j-num">{num}</span>'
        if p is not None:
            return f'<span class="j-punct">{p}</span>'
        return _html.escape(m.group(0))

    # Escape first, then run tokenizer on escaped text? Simpler: escape inside repl,
    # run tokenizer on raw text (above), and escape any gaps.
    out = []
    last = 0
    for m in _JSON_TOKEN.finditer(text):
        if m.start() > last:
            out.append(_html.escape(text[last:m.start()]))
        out.append(repl(m))
        last = m.end()
    if last < len(text):
        out.append(_html.escape(text[last:]))
    return "".join(out)


# ---------------------------------------------------------------
# OpenAPI fetching & normalization
# ---------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_openapi(base_url: str, cache_bust: float) -> dict:
    url = base_url.rstrip("/") + "/openapi.json"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def _resolve_ref(spec: dict, ref: str) -> dict:
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for p in parts:
        node = node[p]
    return node


def _schema_type(sch: dict, spec: dict, depth: int = 0) -> str:
    if depth > 4:
        return "any"
    if not sch:
        return "any"
    if "$ref" in sch:
        return _schema_type(_resolve_ref(spec, sch["$ref"]), spec, depth + 1)
    if "anyOf" in sch or "oneOf" in sch:
        subs = [s for s in (sch.get("anyOf") or sch.get("oneOf") or [])
                if s.get("type") != "null"]
        if subs:
            return _schema_type(subs[0], spec, depth + 1)
        return "any"
    t = sch.get("type")
    if t == "array":
        inner = _schema_type(sch.get("items") or {}, spec, depth + 1)
        return f"list[{inner}]"
    if t == "object":
        return "dict"
    if t == "integer":
        return "int"
    if t == "number":
        return "float"
    if t == "boolean":
        return "bool"
    if sch.get("format") == "date":
        return "date"
    if sch.get("format") == "date-time":
        return "datetime"
    return t or "str"


def _expand_body_fields(sch: dict, spec: dict) -> list[dict]:
    """Flatten a top-level object schema into a field list."""
    if "$ref" in sch:
        sch = _resolve_ref(spec, sch["$ref"])
    props = sch.get("properties") or {}
    required = set(sch.get("required") or [])
    out = []
    for name, psch in props.items():
        ptype = _schema_type(psch, spec)
        out.append({
            "name": name,
            "type": ptype,
            "required": name in required,
            "default": psch.get("default"),
            "desc": psch.get("description") or psch.get("title") or "",
        })
    return out


def normalize_endpoints(spec: dict) -> list[dict]:
    out: list[dict] = []
    paths = spec.get("paths", {}) or {}
    for path, methods in paths.items():
        for method, op in (methods or {}).items():
            if method.lower() not in HTTP_METHODS:
                continue
            tags = op.get("tags") or []
            group = tags[0] if tags else "default"
            summary = op.get("summary") or op.get("description") or ""
            if summary:
                summary = summary.strip().split("\n")[0][:200]

            path_params: list[dict] = []
            query_params: list[dict] = []
            for p in op.get("parameters", []) or []:
                if "$ref" in p:
                    p = _resolve_ref(spec, p["$ref"])
                loc = p.get("in")
                meta = {
                    "name": p.get("name"),
                    "type": _schema_type(p.get("schema") or {}, spec),
                    "required": p.get("required", False),
                    "default": (p.get("schema") or {}).get("default"),
                    "desc": p.get("description") or "",
                }
                if loc == "path":
                    path_params.append(meta)
                elif loc == "query":
                    query_params.append(meta)

            body = None
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            if "application/json" in content:
                sch = content["application/json"].get("schema") or {}
                body = {
                    "type": "json",
                    "fields": _expand_body_fields(sch, spec),
                    "raw_schema": sch,
                }
            elif "multipart/form-data" in content:
                sch = content["multipart/form-data"].get("schema") or {}
                if "$ref" in sch:
                    sch = _resolve_ref(spec, sch["$ref"])
                props = sch.get("properties") or {}
                required = set(sch.get("required") or [])
                file_field = None
                extra = []
                for name, psch in props.items():
                    psch_r = psch
                    if "$ref" in psch_r:
                        psch_r = _resolve_ref(spec, psch_r["$ref"])
                    fmt = (psch_r or {}).get("format")
                    if fmt == "binary":
                        file_field = name
                    else:
                        extra.append({
                            "name": name,
                            "type": _schema_type(psch_r, spec),
                            "required": name in required,
                            "default": psch_r.get("default") if isinstance(psch_r, dict) else None,
                            "desc": psch_r.get("description") if isinstance(psch_r, dict) else "",
                        })
                body = {
                    "type": "multipart",
                    "file_field": file_field or "file",
                    "file_required": (file_field in required) if file_field else False,
                    "extra": extra,
                }

            out.append({
                "key": f"{method.upper()} {path}",
                "group": group,
                "method": method.upper(),
                "path": path,
                "summary": summary,
                "path_params": path_params,
                "query_params": query_params,
                "body": body,
            })
    out.sort(key=lambda e: (e["group"], e["path"], e["method"]))
    return out


# ---------------------------------------------------------------
# Input rendering + coercion
# ---------------------------------------------------------------
def _default_for(t: str) -> Any:
    t = (t or "str").lower()
    if t == "int": return 0
    if t == "float": return 0.0
    if t == "bool": return False
    if t.startswith("list"): return []
    if t == "dict": return {}
    return ""


def render_param(p: dict, key_prefix: str) -> Any:
    name = p["name"]
    ptype = (p.get("type") or "str").lower()
    required = p.get("required", False)
    default = p.get("default")
    desc = p.get("desc") or ""
    label = f"{name}" + (" *" if required else "")
    key = f"{key_prefix}__{name}"
    help_txt = ptype + (f" — {desc}" if desc else "")

    default_val = default if default is not None else _default_for(ptype)

    if ptype == "bool":
        return st.checkbox(label, value=bool(default) if default is not None else False, key=key, help=help_txt)
    if ptype.startswith("list"):
        val = ",".join(map(str, default_val)) if default_val else ""
        return st.text_input(label, value=val, key=key, help=help_txt + " (comma-separated)", placeholder="a,b,c")
    if ptype == "dict":
        val = json.dumps(default_val, indent=2) if default_val else "{}"
        return st.text_area(label, value=val, key=key, help=help_txt + " (JSON)", height=100)
    placeholder = {
        "int": "integer", "float": "number",
        "date": "YYYY-MM-DD", "datetime": "YYYY-MM-DDTHH:MM:SS",
    }.get(ptype, ptype + (" (required)" if required else " (optional)"))
    return st.text_input(
        label,
        value="" if default is None else str(default_val),
        key=key, help=help_txt, placeholder=placeholder,
    )


def coerce(raw: Any, ptype: str, required: bool) -> tuple[bool, Any]:
    ptype = (ptype or "str").lower()
    if isinstance(raw, bool):
        return True, raw
    if raw is None or raw == "":
        return (False, None) if not required else (True, None)
    s = str(raw).strip()
    if ptype == "int": return True, int(s)
    if ptype == "float": return True, float(s)
    if ptype == "list[int]":
        return True, [int(x.strip()) for x in s.split(",") if x.strip()]
    if ptype.startswith("list"):
        return True, [x.strip() for x in s.split(",") if x.strip()]
    if ptype == "dict":
        return True, json.loads(s) if s else {}
    if ptype == "bool":
        return True, s.lower() in ("true", "1", "yes", "y")
    return True, s


def build_request(ep: dict, inputs: dict) -> dict:
    base = st.session_state.base_url.rstrip("/")
    path = ep["path"]
    errors: list[str] = []

    for p in ep.get("path_params") or []:
        raw = inputs.get(f"path__{p['name']}", "")
        try:
            ok, v = coerce(raw, p["type"], True)
        except Exception as e:
            errors.append(f"{p['name']}: {e}"); continue
        if not ok or v in (None, ""):
            errors.append(f"{p['name']} is required (path)"); continue
        path = path.replace("{" + p["name"] + "}", str(v))

    query: dict[str, Any] = {}
    for p in ep.get("query_params") or []:
        raw = inputs.get(f"query__{p['name']}")
        try:
            ok, v = coerce(raw, p["type"], p.get("required", False))
        except Exception as e:
            errors.append(f"{p['name']}: {e}"); continue
        if not ok:
            if p.get("required"):
                errors.append(f"{p['name']} is required (query)")
            continue
        if v is None and p.get("required"):
            errors.append(f"{p['name']} is required (query)"); continue
        if v is not None:
            query[p["name"]] = v

    body_json = None
    files = None
    data = None
    body = ep.get("body")
    if body:
        if body["type"] == "json":
            mode = inputs.get("__body_mode", "form")
            if mode == "raw":
                raw = inputs.get("__body_raw", "")
                try:
                    body_json = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError as e:
                    errors.append(f"body JSON: {e}")
            else:
                obj: dict[str, Any] = {}
                for f in body.get("fields") or []:
                    raw = inputs.get(f"body__{f['name']}")
                    try:
                        ok, v = coerce(raw, f["type"], f.get("required", False))
                    except Exception as e:
                        errors.append(f"{f['name']}: {e}"); continue
                    if ok and v is not None:
                        obj[f["name"]] = v
                    elif f.get("required"):
                        errors.append(f"{f['name']} is required (body)")
                body_json = obj
        elif body["type"] == "multipart":
            files_map = {}
            ff = body.get("file_field", "file")
            up = inputs.get(f"__file__{ff}")
            if up is not None:
                files_map[ff] = (up.name, up.getvalue())
            elif body.get("file_required"):
                errors.append(f"{ff} file is required")
            data_map: dict[str, Any] = {}
            for f in body.get("extra") or []:
                raw = inputs.get(f"form__{f['name']}")
                try:
                    ok, v = coerce(raw, f["type"], f.get("required", False))
                except Exception as e:
                    errors.append(f"{f['name']}: {e}"); continue
                if ok and v is not None:
                    data_map[f["name"]] = v
                elif f.get("required"):
                    errors.append(f"{f['name']} is required (form)")
            files = files_map or None
            data = data_map or None

    return {
        "method": ep["method"], "url": base + path,
        "params": query or None, "json": body_json,
        "files": files, "data": data, "errors": errors,
    }


def send_request(req: dict, timeout: int = 60) -> dict:
    t0 = time.time()
    try:
        r = requests.request(
            method=req["method"], url=req["url"],
            params=req.get("params"),
            json=req.get("json") if not req.get("files") else None,
            files=req.get("files"),
            data=req.get("data") if req.get("files") else None,
            timeout=timeout,
        )
        ms = int((time.time() - t0) * 1000)
        try:
            body = r.json()
        except Exception:
            body = r.text
        return {"ok": True, "status": r.status_code, "ms": ms,
                "headers": dict(r.headers), "body": body, "url": r.url}
    except requests.RequestException as e:
        return {"ok": False, "status": None,
                "ms": int((time.time() - t0) * 1000),
                "error": str(e), "url": req["url"]}


# ---------------------------------------------------------------
# Sidebar: base URL + schema load + picker
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🧪 API Tester")
    st.caption("Live from FastAPI /openapi.json")

    st.session_state.base_url = st.text_input(
        "Base URL", value=st.session_state.base_url,
        help="e.g. http://localhost:8000",
    )

    col_l, col_r = st.columns([1, 1])
    with col_l:
        reload_clicked = st.button("🔄 Reload schema", use_container_width=True)
    with col_r:
        clear_hist = st.button("🗑️ Clear history", use_container_width=True)

    if clear_hist:
        st.session_state.history = []

    if reload_clicked or st.session_state.schema is None:
        try:
            spec = fetch_openapi(
                st.session_state.base_url,
                cache_bust=time.time() if reload_clicked else 0.0,
            )
            st.session_state.schema = normalize_endpoints(spec)
            st.session_state.schema_error = None
            if st.session_state.selected_key is None and st.session_state.schema:
                st.session_state.selected_key = st.session_state.schema[0]["key"]
        except Exception as e:
            st.session_state.schema_error = str(e)

    if st.session_state.schema_error:
        st.error(f"Could not load schema:\n{st.session_state.schema_error}")
        st.stop()

    endpoints = st.session_state.schema or []
    if not endpoints:
        st.warning("No endpoints loaded yet.")
        st.stop()

    st.divider()

    col_q, col_m = st.columns([2, 1])
    with col_q:
        st.session_state.filter_text = st.text_input(
            "🔍 Search", value=st.session_state.filter_text,
            placeholder="path, tag, summary…",
        )
    with col_m:
        methods = ["ALL", "GET", "POST", "PUT", "PATCH", "DELETE"]
        st.session_state.method_filter = st.selectbox(
            "Method", methods,
            index=methods.index(st.session_state.method_filter),
        )

    q = st.session_state.filter_text.lower().strip()
    mf = st.session_state.method_filter

    def _match(e: dict) -> bool:
        if mf != "ALL" and e["method"] != mf:
            return False
        if not q:
            return True
        blob = f"{e['group']} {e['method']} {e['path']} {e.get('summary','')}".lower()
        return q in blob

    filtered = [e for e in endpoints if _match(e)]
    st.caption(f"**{len(filtered)}** of {len(endpoints)} endpoints")

    grouped: dict[str, list[dict]] = {}
    for e in filtered:
        grouped.setdefault(e["group"], []).append(e)

    for group, items in sorted(grouped.items()):
        with st.expander(f"📁 {group}  ({len(items)})", expanded=bool(q)):
            for e in items:
                is_sel = e["key"] == st.session_state.selected_key
                if st.button(
                    f"{e['method']:6s}  {e['path']}",
                    key=f"pick__{e['key']}",
                    use_container_width=True,
                    type="primary" if is_sel else "secondary",
                ):
                    st.session_state.selected_key = e["key"]
                    st.rerun()


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
endpoints = st.session_state.schema or []
ep = next((e for e in endpoints if e["key"] == st.session_state.selected_key), endpoints[0])

left, right = st.columns([1.1, 1], gap="large")

with left:
    st.markdown(
        f'{method_badge(ep["method"])} '
        f'<span class="path-text" style="font-size:1.1rem;">{ep["path"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="summary-box"><b>{ep["group"]}</b>'
        f'{" — " + ep["summary"] if ep["summary"] else ""}</div>',
        unsafe_allow_html=True,
    )

    inputs: dict[str, Any] = {}

    if ep.get("path_params"):
        st.markdown("##### 🔗 Path params")
        for p in ep["path_params"]:
            inputs[f"path__{p['name']}"] = render_param(p, "path")

    if ep.get("query_params"):
        st.markdown("##### 🧭 Query params")
        cols = st.columns(2)
        for i, p in enumerate(ep["query_params"]):
            with cols[i % 2]:
                inputs[f"query__{p['name']}"] = render_param(p, "query")

    body = ep.get("body")
    if body:
        if body["type"] == "json":
            st.markdown("##### 📦 Body (JSON)")
            mode = st.radio(
                "Mode", ["form", "raw"], horizontal=True,
                key=f"body_mode_{ep['key']}", label_visibility="collapsed",
            )
            inputs["__body_mode"] = mode
            fields = body.get("fields") or []
            if mode == "form":
                if fields:
                    cols = st.columns(2)
                    for i, f in enumerate(fields):
                        with cols[i % 2]:
                            inputs[f"body__{f['name']}"] = render_param(f, "body")
                else:
                    st.caption("No declared fields — switch to raw mode.")
            else:
                template = {f["name"]: _default_for(f["type"]) for f in fields}
                inputs["__body_raw"] = st.text_area(
                    "JSON",
                    value=json.dumps(template, indent=2) if template else "{}",
                    height=260, key=f"body_raw_{ep['key']}",
                )
        elif body["type"] == "multipart":
            st.markdown("##### 📎 Multipart body")
            ff = body.get("file_field", "file")
            inputs[f"__file__{ff}"] = st.file_uploader(
                f"{ff}" + (" *" if body.get("file_required") else ""),
                key=f"upload_{ep['key']}_{ff}",
            )
            for f in body.get("extra") or []:
                inputs[f"form__{f['name']}"] = render_param(f, "form")

    st.divider()

    req = build_request(ep, inputs)
    attempted_key = f"__tried__{ep['key']}"
    if st.session_state.get(attempted_key) and req["errors"]:
        for err in req["errors"]:
            st.warning(f"⚠️  {err}")

    with st.expander("👁️  Request preview", expanded=False):
        preview = {
            "method": req["method"], "url": req["url"],
            "query_params": req.get("params"),
            "json_body": req.get("json"),
            "files": list((req.get("files") or {}).keys()) if req.get("files") else None,
            "form_data": req.get("data"),
        }
        st.code(json.dumps(preview, indent=2, default=str), language="json")
        curl = [f"curl -X {req['method']}"]
        url_show = req["url"]
        if req.get("params"):
            url_show += "?" + urlencode(
                {k: v for k, v in req["params"].items() if v is not None}, doseq=True
            )
        curl.append(f"'{url_show}'")
        if req.get("json") is not None and not req.get("files"):
            curl.append("-H 'Content-Type: application/json'")
            curl.append(f"-d '{json.dumps(req['json'])}'")
        if req.get("files"):
            for k in req["files"]:
                curl.append(f"-F '{k}=@/path/to/file'")
        st.code(" \\\n  ".join(curl), language="bash")

    col_send, _ = st.columns([1, 3])
    with col_send:
        send = st.button(
            f"▶ Send  {ep['method']}",
            type="primary", use_container_width=True,
        )

    if send:
        st.session_state[attempted_key] = True
        if req["errors"]:
            st.rerun()
        with st.spinner("Sending…"):
            resp = send_request(req)
        st.session_state.last_response = resp
        st.session_state.history.insert(0, {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "method": ep["method"], "path": ep["path"],
            "status": resp.get("status"), "ms": resp.get("ms"),
        })
        st.session_state.history = st.session_state.history[:30]


with right:
    st.markdown("### 📨 Response")
    resp = st.session_state.last_response
    if not resp:
        st.info("Send a request to see the response here.")
    else:
        status = resp.get("status")
        ms = resp.get("ms")
        if status is None:
            css, label = "status-err", "ERROR"
        elif 200 <= status < 300:
            css, label = "status-ok", f"{status}"
        elif 400 <= status < 500:
            css, label = "status-warn", f"{status}"
        else:
            css, label = "status-err", f"{status}"

        cols = st.columns(3)
        cols[0].markdown(f'**Status** <span class="{css}">{label}</span>', unsafe_allow_html=True)
        cols[1].markdown(f"**Time** `{ms} ms`")
        if resp.get("url"):
            cols[2].markdown(f"**URL** `…{resp['url'][-40:]}`")

        if not resp.get("ok"):
            st.error(resp.get("error", "request failed"))
        else:
            tab_body, tab_hdr = st.tabs(["Body", "Headers"])
            with tab_body:
                body = resp.get("body")
                is_json = isinstance(body, (dict, list))
                if is_json:
                    body_text = json.dumps(body, indent=2, default=str)
                    rendered = highlight_json(body_text)
                else:
                    body_text = str(body)
                    rendered = _html.escape(body_text)
                render_code_html(rendered)
                if is_json:
                    st.download_button(
                        "⬇️ Download JSON",
                        data=body_text,
                        file_name=f"response_{int(time.time())}.json",
                        mime="application/json",
                    )
            with tab_hdr:
                hdr_text = json.dumps(resp.get("headers", {}), indent=2)
                render_code_html(highlight_json(hdr_text))

    st.markdown("### 🕘 History")
    if not st.session_state.history:
        st.caption("No calls yet this session.")
    else:
        for h in st.session_state.history[:10]:
            s = h["status"]
            if s is None:
                tag = "🔴"
            elif 200 <= s < 300:
                tag = "🟢"
            elif 400 <= s < 500:
                tag = "🟡"
            else:
                tag = "🔴"
            st.markdown(
                f"{tag} `{h['ts']}`  **{h['method']}** `{h['path']}`  → "
                f"`{s}` · {h['ms']}ms"
            )
