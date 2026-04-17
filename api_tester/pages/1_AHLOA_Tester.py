"""
AHLOA API Tester — Streamlit UI

Layout:
  Sidebar: Admin, User Management, Filters
  Main: 8 tabs — 4 Construction + 4 Survey (Gantt, Calendar, Weekly, Analytics)

Run:
    streamlit run api_tester/ahloa_tester.py
"""
from __future__ import annotations
import json, io, csv, time
from datetime import date, timedelta
import requests
import streamlit as st
import pandas as pd

st.set_page_config(page_title="AHLOA Tester", page_icon="🏗️", layout="wide")
st.markdown("""<style>
.main > div { padding-top: 0.3rem; }
div[data-testid="stSidebar"] { width: 330px !important; }
.pass { color: #22c55e; font-weight: 700; }
.fail { color: #ef4444; font-weight: 700; }
.section-hdr { font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;
               letter-spacing: 1px; margin: 10px 0 5px 0; }
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------
def _call(method, path, params=None, json_body=None, files=None):
    try:
        url = f"{st.session_state.get('base','http://localhost:8000')}/api/v1/schedular{path}"
        r = getattr(requests, method)(url, params=params, json=json_body, files=files, timeout=30)
        return r.status_code, r.json() if r.status_code < 500 else {"error": r.text[:300]}
    except Exception as e:
        return 0, {"error": str(e)}

def GET(p, q=None): return _call("get", p, q)
def POST(p, q=None, j=None, f=None): return _call("post", p, q, j, f)
def PUT(p, q=None, j=None): return _call("put", p, q, j)
def DELETE(p, q=None): return _call("delete", p, q)

def badge(code):
    c = "pass" if 200 <= code < 300 else "fail"
    st.markdown(f'<span class="{c}">HTTP {code}</span>', unsafe_allow_html=True)

def fparams(**extra):
    """Build filter params from sidebar state."""
    p = {}
    uid = st.session_state.get("user_id", "")
    if uid: p["user_id"] = uid
    for k in ("region", "market", "site_id", "vendor"):
        v = st.session_state.get(f"f_{k}", "")
        if v: p[k] = v
    if st.session_state.get("pace_flag"): p["pace_constraint_flag"] = "true"
    if st.session_state.get("vc_flag"): p["consider_vendor_capacity"] = "true"
    p.update(extra)
    return p

def sites_df(sites):
    return pd.DataFrame([{
        "site_id": s.get("site_id"), "project_id": s.get("project_id"),
        "market": s.get("market"), "region": s.get("region"),
        "vendor": s.get("vendor_name"), "gc_note": s.get("gc_note"),
        "cx_date": s.get("forecasted_cx_start_date"),
        "cx_source": s.get("forecasted_cx_source"),
        "status": s.get("overall_status"),
        "on_track_%": s.get("on_track_pct"),
        "milestones": len(s.get("milestones", [])),
    } for s in sites]) if sites else pd.DataFrame()

def ms_df(milestones):
    return pd.DataFrame([{
        "key": m.get("key"), "name": m.get("name"),
        "expected": m.get("expected_date"), "actual": m.get("actual_finish"),
        "status": m.get("status"), "delay": m.get("delay_days"),
        "phase": m.get("phase_type"),
    } for m in milestones]) if milestones else pd.DataFrame()

# ---------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------
with st.sidebar:
    st.title("🏗️ AHLOA Tester")
    st.session_state["base"] = st.text_input("Backend URL", "http://localhost:8000")
    st.session_state["user_id"] = st.text_input("User ID", "test_user")
    uid = st.session_state["user_id"]

    # ---- ADMIN SECTION ----
    st.markdown('<p class="section-hdr">Admin</p>', unsafe_allow_html=True)
    admin_action = st.selectbox("Admin Action", ["—", "View AHLOA Milestones", "Create Prerequisite"])

    # ---- USER SECTION ----
    st.markdown('<p class="section-hdr">User Management</p>', unsafe_allow_html=True)
    user_action = st.selectbox("User Action", [
        "—", "Skip Prereq (market-wise)", "Unskip Prereq", "List My Skips",
        "Create Pace Constraint", "List Pace Constraints", "Delete Pace Constraint",
        "Update SLA (expected_days)", "List My SLA Overrides",
        "Upload Excel (CX Override)", "List My Uploads", "Delete My Uploads",
    ])

    # ---- FILTERS ----
    st.markdown('<p class="section-hdr">Filters</p>', unsafe_allow_html=True)
    st.session_state["f_region"] = st.text_input("Region", "", key="fr")
    st.session_state["f_market"] = st.text_input("Market", "", key="fm")
    st.session_state["f_site_id"] = st.text_input("Site ID", "", key="fs")
    st.session_state["f_vendor"] = st.text_input("Vendor", "", key="fv")
    st.session_state["pace_flag"] = st.checkbox("Pace Constraints", key="pf")
    st.session_state["vc_flag"] = st.checkbox("Vendor Capacity", key="vc")

# ---------------------------------------------------------------
# Admin / User action panel (above tabs)
# ---------------------------------------------------------------
if admin_action != "—" or user_action != "—":
    st.divider()

# ---- ADMIN ACTIONS ----
if admin_action == "View AHLOA Milestones":
    st.subheader("Admin — AHLOA Milestone Definitions")
    if st.button("Load AHLOA Milestones"):
        code, data = GET("/admin/ahloa/prerequisites" if False else "/prerequisites", {"project_type": "ahloa"})
        badge(code)
        if code == 200 and isinstance(data, list):
            st.dataframe(pd.DataFrame(data), use_container_width=True)
        elif code == 200:
            st.json(data)

elif admin_action == "Create Prerequisite":
    st.subheader("Admin — Create AHLOA Prerequisite")
    c1, c2 = st.columns(2)
    mk = c1.text_input("Key (unique)", "", key="adm_key")
    mn = c2.text_input("Name", "", key="adm_name")
    c3, c4, c5 = st.columns(3)
    ed = c3.number_input("Expected Days", 0, 365, 0, key="adm_ed")
    to = c4.text_input("Task Owner", "", key="adm_to")
    pt = c5.text_input("Phase Type", "", key="adm_pt")
    st.markdown("**Column Mapping**")
    c6, c7 = st.columns(2)
    col_name = c6.text_input("Staging Column Name", "", key="adm_cn")
    col_role = c7.selectbox("Column Role", ["date", "text", "status"], key="adm_cr")
    dep = st.text_input("Depends On (milestone key, optional)", "", key="adm_dep")

    if st.button("Create", type="primary") and mk and mn:
        body = {
            "key": mk, "name": mn, "expected_days": ed,
            "task_owner": to or None, "phase_type": pt or None,
            "preceding_milestone_keys": [dep] if dep else [],
            "following_milestone_keys": [],
            "columns": [{"column_name": col_name, "column_role": col_role, "logic": None}] if col_name else [],
        }
        code, data = POST("/admin/prerequisites", {"project_type": "ahloa"}, body)
        badge(code)
        if code == 200:
            st.success(f"Created AHLOA prerequisite '{mk}'")
        st.json(data)

# ---- USER ACTIONS ----
if user_action == "Skip Prereq (market-wise)":
    st.subheader("User Skip — Market-Wise (AHLOA)")
    c1, c2 = st.columns(2)
    mk = c1.text_input("Milestone Key", "3850")
    mkt = c2.text_input("Market (empty=all markets)", "")
    if st.button("Skip for me"):
        body = {"user_id": uid, "milestone_key": mk}
        if mkt: body["market"] = mkt
        code, data = POST("/skip-prerequisites", {"project_type": "ahloa"}, body)
        badge(code); st.json(data)

elif user_action == "Unskip Prereq":
    st.subheader("User Unskip (AHLOA)")
    c1, c2 = st.columns(2)
    mk = c1.text_input("Milestone Key", "3850")
    mkt = c2.text_input("Market (optional)", "")
    if st.button("Unskip"):
        p = {"project_type": "ahloa"}
        if mkt: p["market"] = mkt
        code, data = DELETE(f"/skip-prerequisites/{uid}/{mk}", p)
        badge(code); st.json(data)

elif user_action == "List My Skips":
    st.subheader("My Skipped Prerequisites (AHLOA)")
    mkt = st.text_input("Filter market (optional)", "")
    if st.button("List"):
        p = {"project_type": "ahloa"}
        if mkt: p["market"] = mkt
        code, data = GET(f"/skip-prerequisites/{uid}", p)
        badge(code)
        if code == 200:
            st.metric("Count", len(data))
            if data: st.dataframe(pd.DataFrame(data), use_container_width=True)

elif user_action == "Create Pace Constraint":
    st.subheader("Create Pace Constraint")
    gl = st.selectbox("Geo Level", ["market", "area", "region"])
    gv = st.text_input(f"{gl.title()} value", "")
    mx = st.number_input("Max sites/week", 1, 100, 5)
    if st.button("Create") and gv:
        code, data = POST("/pace-constraints", json_body={"user_id": uid, "max_sites": mx, gl: gv})
        badge(code); st.json(data)

elif user_action == "List Pace Constraints":
    if st.button("List"):
        code, data = GET("/pace-constraints", {"user_id": uid})
        badge(code)
        if code == 200 and data: st.dataframe(pd.DataFrame(data), use_container_width=True)

elif user_action == "Delete Pace Constraint":
    eid = st.number_input("Constraint ID", 1, 99999, 1)
    if st.button("Delete"):
        code, data = DELETE(f"/pace-constraints/{eid}", {"user_id": uid})
        badge(code); st.json(data)

elif user_action == "Update SLA (expected_days)":
    st.subheader("User SLA Override (expected_days)")
    mk = st.text_input("Milestone Key", "3850")
    ed = st.number_input("Expected Days", 0, 365, 30)
    if st.button("Save Override"):
        code, data = PUT(f"/user-expected-days/{uid}", json_body={"milestone_key": mk, "expected_days": ed})
        badge(code); st.json(data)

elif user_action == "List My SLA Overrides":
    if st.button("List"):
        code, data = GET(f"/user-expected-days/{uid}")
        badge(code)
        if code == 200: st.json(data)

elif user_action == "Upload Excel (CX Override)":
    st.subheader("Upload CX Start Date (Excel/CSV)")
    uf = st.file_uploader("File", type=["csv", "xlsx", "xls"])
    st.caption("Columns: SITE_ID, REGION, MARKET, PROJECT_ID, pj_p_4225_construction_start_finish")
    if not uf:
        st.markdown("**Or quick test:**")
        c1, c2, c3 = st.columns(3)
        ts = c1.text_input("Site ID", ""); tp = c2.text_input("Project ID", "")
        td = c3.date_input("CX Date", date.today() + timedelta(180))
        if st.button("Generate & Upload") and ts:
            buf = io.StringIO()
            csv.writer(buf).writerows([["SITE_ID","REGION","MARKET","PROJECT_ID","pj_p_4225_construction_start_finish"],[ts,"","",tp,str(td)]])
            code, data = POST("/excel-upload/upload", {"user_id": uid, "project_type": "ahloa"},
                              f={"file": ("test.csv", io.BytesIO(buf.getvalue().encode()), "text/csv")})
            badge(code); st.json(data)
    elif st.button("Upload"):
        code, data = POST("/excel-upload/upload", {"user_id": uid, "project_type": "ahloa"},
                          f={"file": (uf.name, uf, uf.type)})
        badge(code); st.json(data)

elif user_action == "List My Uploads":
    if st.button("List"):
        code, data = GET("/excel-upload", {"user_id": uid, "project_type": "ahloa"})
        badge(code)
        if code == 200:
            st.metric("Rows", data.get("total"))
            if data.get("data"): st.dataframe(pd.DataFrame(data["data"]), use_container_width=True)

elif user_action == "Delete My Uploads":
    if st.button("Delete All My Uploads"):
        code, data = DELETE("/excel-upload", {"user_id": uid, "project_type": "ahloa"})
        badge(code); st.json(data)

# ---------------------------------------------------------------
# Main area: 8 tabs (4 Construction + 4 Survey)
# ---------------------------------------------------------------
st.divider()
t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
    "🏗️ Construction Gantt", "📅 Construction Calendar",
    "📊 Construction Weekly", "📈 Construction Analytics",
    "🔬 Survey Gantt", "📅 Survey Calendar",
    "📊 Survey Weekly", "📈 Survey Analytics",
])

# ---- helper to render gantt tab ----
def render_gantt(tab_name):
    ep = "gantt-chart-construction" if tab_name == "construction" else "gantt-chart-scope"
    c1, c2 = st.columns(2)
    ps = c1.number_input("Page Size", 5, 50, 10, key=f"ps_{tab_name}")
    pg = c2.number_input("Page", 1, 2000, 1, key=f"pg_{tab_name}")
    if st.button("Fetch", type="primary", key=f"fetch_gantt_{tab_name}"):
        code, data = GET(f"/ahloa/{ep}", fparams(limit=ps, offset=(pg-1)*ps))
        badge(code)
        if code == 200:
            sites = data.get("sites", [])
            total = data.get("total_count", 0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total", total); c2.metric("Page", f"{pg}/{max(1,-(-total//ps))}"); c3.metric("Showing", len(sites))
            if sites:
                st.dataframe(sites_df(sites), use_container_width=True, height=300)
                sel = st.selectbox("Detail", [f"{s['site_id']} / {s.get('project_id','')}" for s in sites], key=f"sel_{tab_name}")
                idx = [f"{s['site_id']} / {s.get('project_id','')}" for s in sites].index(sel)
                s = sites[idx]
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("CX", s.get("forecasted_cx_start_date","—")); c2.metric("Source", s.get("forecasted_cx_source","—"))
                c3.metric("Status", s.get("overall_status","—")); c4.metric("GC", s.get("vendor_name") or s.get("gc_note","—"))
                st.dataframe(ms_df(s.get("milestones",[])), use_container_width=True)

def render_calendar(tab_name):
    c1, c2 = st.columns(2)
    sd = c1.date_input("From", date.today()-timedelta(30), key=f"csd_{tab_name}")
    ed = c2.date_input("To", date.today()+timedelta(365), key=f"ced_{tab_name}")
    if st.button("Fetch", type="primary", key=f"fetch_cal_{tab_name}"):
        code, data = GET("/calendar", fparams(project_type="ahloa", tab=tab_name, start_date=str(sd), end_date=str(ed)))
        badge(code)
        if code == 200:
            sites = data.get("sites", [])
            st.metric("Sites", len(sites))
            if sites: st.dataframe(sites_df(sites[:100]), use_container_width=True)
            if len(sites) > 100: st.caption(f"Showing 100/{len(sites)}")

def render_weekly(tab_name):
    if st.button("Fetch", type="primary", key=f"fetch_wk_{tab_name}"):
        code, data = GET("/dashboard/weekly-status-sla-default", fparams(project_type="ahloa", tab=tab_name))
        badge(code)
        if code == 200:
            weeks = data.get("weeks", [])
            st.metric("Weeks", len(weeks))
            if weeks:
                rows = []
                for w in weeks:
                    row = {"week": w["week"], "year": w["year"], "start": w["week_start"], "total": w["total"]}
                    for rn, cnts in w.get("status_counts", {}).items():
                        for s, c in cnts.items(): row[f"{rn}|{s}"] = c
                    rows.append(row)
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

def render_analytics(tab_name):
    sub = st.radio("View", ["Pending Milestones", "By Milestone", "Drilldown"], horizontal=True, key=f"an_{tab_name}")
    if sub == "Pending Milestones" and st.button("Fetch", key=f"an1_{tab_name}"):
        code, data = GET("/analytics/pending-milestones/auto", fparams(project_type="ahloa", tab=tab_name))
        badge(code)
        if code == 200:
            c1,c2 = st.columns(2); c1.metric("Total", data.get("total_sites")); c2.metric("Blocked", data.get("blocked_sites"))
            b = data.get("pending_milestones", [])
            if b:
                df = pd.DataFrame(b)
                st.bar_chart(df.set_index("pending_milestone_count")["site_count"])
                st.dataframe(df, use_container_width=True)
    elif sub == "By Milestone" and st.button("Fetch", key=f"an2_{tab_name}"):
        code, data = GET("/analytics/pending-by-milestone/auto", fparams(project_type="ahloa", tab=tab_name))
        badge(code)
        if code == 200:
            ms = data.get("milestones", [])
            if ms:
                df = pd.DataFrame(ms)
                st.bar_chart(df.set_index("milestone_name")["pending_count"])
                st.dataframe(df, use_container_width=True)
    elif sub == "Drilldown":
        dt = st.selectbox("Type", ["pending_count", "milestone_key"], key=f"dt_{tab_name}")
        pc = st.number_input("Count", 0, 20, 5, key=f"pc_{tab_name}") if dt == "pending_count" else None
        mk = st.text_input("Key", "cpo", key=f"mk_{tab_name}") if dt == "milestone_key" else None
        if st.button("Fetch", key=f"an3_{tab_name}"):
            p = fparams(project_type="ahloa", tab=tab_name, drilldown_type=dt)
            if pc is not None: p["pending_count"] = pc
            if mk: p["milestone_key"] = mk
            code, data = GET("/analytics/drilldown/auto", p)
            badge(code)
            if code == 200:
                st.metric("Sites", len(data.get("sites", [])))
                if data.get("sites"): st.dataframe(sites_df(data["sites"][:50]), use_container_width=True)

# ---- Render tabs ----
with t1: render_gantt("construction")
with t2: render_calendar("construction")
with t3: render_weekly("construction")
with t4: render_analytics("construction")
with t5: render_gantt("survey")
with t6: render_calendar("survey")
with t7: render_weekly("survey")
with t8: render_analytics("survey")
