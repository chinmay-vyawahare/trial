    # (skipped milestones are already excluded from milestone_status_summary)
    def _aggregate_milestone_detail(site_list):
        total_ms = 0
        on_track_ms = 0
        in_progress_ms = 0
        delayed_ms = 0
        for s in site_list:
            ms_summary = s.get("milestone_status_summary", {})
            total_ms += ms_summary.get("total", 0)
            on_track_ms += ms_summary.get("on_track", 0)
            in_progress_ms += ms_summary.get("in_progress", 0)
            delayed_ms += ms_summary.get("delayed", 0)
        return {
            "total_milestones": total_ms,
            "on_track_milestones": on_track_ms,
            "in_progress_milestones": in_progress_ms,
            "delayed_milestones": delayed_ms,
            "on_track_pct": round((on_track_ms / total_ms * 100), 2) if total_ms > 0 else 0,
            "in_progress_pct": round((in_progress_ms / total_ms * 100), 2) if total_ms > 0 else 0,
            "delayed_pct": round((delayed_ms / total_ms * 100), 2) if total_ms > 0 else 0,
        }

    on_track_sites_list = [s for s in countable if s["overall_status"] == "ON TRACK"]
    in_progress_sites_list = [s for s in countable if s["overall_status"] == "IN PROGRESS"]
    critical_sites_list = [s for s in countable if s["overall_status"] == "CRITICAL"]
    blocked_sites_list = [s for s in sites if s["overall_status"] == "Blocked"]

    # Build threshold definitions for UI display
    # Get typical total milestones per site (from first non-blocked site)
    typical_total_ms = 0
    for s in countable:
        ms_summary = s.get("milestone_status_summary", {})
        if ms_summary.get("total", 0) > 0:
            typical_total_ms = ms_summary["total"]
            break

    ms_thresholds = get_milestone_thresholds(config_db)
    threshold_defs = {}
    for t in ms_thresholds:
        min_count = math.ceil(t["min_pct"] / 100 * typical_total_ms) if typical_total_ms > 0 else 0
        max_count = math.floor(t["max_pct"] / 100 * typical_total_ms) if (t["max_pct"] is not None and typical_total_ms > 0) else typical_total_ms
        threshold_defs[t["status_label"]] = {
            "min_pct": t["min_pct"],
            "max_pct": t["max_pct"],
            "milestone_range": f"{min_count}-{max_count}/{typical_total_ms}",
            "description": (
                f"{t['min_pct']}%+ milestones on track ({min_count}-{max_count}/{typical_total_ms})"
                if t["max_pct"] is None
                else f"{t['min_pct']}%-{t['max_pct']}% milestones on track ({min_count}-{max_count}/{typical_total_ms})"
            ),
        }
    # Fallback if no DB thresholds
    if not threshold_defs:
        min_ot = math.ceil(60 / 100 * typical_total_ms) if typical_total_ms > 0 else 0
        min_ip = math.ceil(30 / 100 * typical_total_ms) if typical_total_ms > 0 else 0
        max_ip = math.floor(59.99 / 100 * typical_total_ms) if typical_total_ms > 0 else 0
        max_cr = math.floor(29.99 / 100 * typical_total_ms) if typical_total_ms > 0 else 0
        threshold_defs = {
            "ON TRACK": {"min_pct": 60, "max_pct": None, "milestone_range": f"{min_ot}-{typical_total_ms}/{typical_total_ms}", "description": f"60%+ milestones on track ({min_ot}-{typical_total_ms}/{typical_total_ms})"},
            "IN PROGRESS": {"min_pct": 30, "max_pct": 59.99, "milestone_range": f"{min_ip}-{max_ip}/{typical_total_ms}", "description": f"30%-59.99% milestones on track ({min_ip}-{max_ip}/{typical_total_ms})"},
            "CRITICAL": {"min_pct": 0, "max_pct": 29.99, "milestone_range": f"0-{max_cr}/{typical_total_ms}", "description": f"0%-29.99% milestones on track (0-{max_cr}/{typical_total_ms})"},
        }


 _empty_detail = {"site_count": 0, "total_milestones": 0, "on_track_milestones": 0, "in_progress_milestones": 0, "delayed_milestones": 0, "on_track_pct": 0, "in_progress_pct": 0, "delayed_pct": 0}
 _empty_threshold = {"min_pct": 0, "max_pct": None, "milestone_range": "0-0/0", "description": ""}
 
 
 
         "status_details": {
            "ON TRACK": {**_empty_detail, "threshold": {**_empty_threshold}},
            "IN PROGRESS": {**_empty_detail, "threshold": {**_empty_threshold}},
            "CRITICAL": {**_empty_detail, "threshold": {**_empty_threshold}},
            "Blocked": {**_empty_detail},
        },
         
         
        "status_details": {
            "ON TRACK": {
                "site_count": on_track,
                "threshold": threshold_defs.get("ON TRACK", {}),
                **_aggregate_milestone_detail(on_track_sites_list),
            },
            "IN PROGRESS": {
                "site_count": in_progress,
                "threshold": threshold_defs.get("IN PROGRESS", {}),
                **_aggregate_milestone_detail(in_progress_sites_list),
            },
            "CRITICAL": {
                "site_count": critical,
                "threshold": threshold_defs.get("CRITICAL", {}),
                **_aggregate_milestone_detail(critical_sites_list),
            },
            "Blocked": {
                "site_count": blocked,
                **_aggregate_milestone_detail(blocked_sites_list),
            },
        },  