    # ----------------------------------------------------------------
    # Data-discrepancy fix: if a milestone has no actual date but ALL
    # of its following (downstream) milestones have actual finish dates,
    # mark it as "On Track" — the work must have been completed.
    # ----------------------------------------------------------------
    key_to_ms_idx = {m["key"]: i for i, m in enumerate(milestones)}
    # Build following map by key (not name)
    following_keys_map: Dict[str, List[str]] = {}
    for ms_cfg in milestones_config:
        k = ms_cfg["key"]
        if k in skipped:
            continue
        dep = ms_cfg["depends_on"]
        if dep is None:
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        for d in dep_list:
            if d not in skipped:
                following_keys_map.setdefault(d, []).append(k)

    for i, m in enumerate(milestones):
        if m.get("is_virtual"):
            continue
        # Only apply to milestones without an actual date
        if m["actual_finish"] is not None:
            continue
        followers = following_keys_map.get(m["key"], [])
        if not followers:
            continue
        # Check if ALL following milestones have actual finish dates
        all_followers_completed = True
        for fk in followers:
            if fk not in key_to_ms_idx:
                all_followers_completed = False
                break
            follower = milestones[key_to_ms_idx[fk]]
            if follower["actual_finish"] is None:
                all_followers_completed = False
                break
        if all_followers_completed:
            milestones[i]["status"] = "On Track"
            milestones[i]["delay_days"] = 0

    # ----------------------------------------------------------------
  




if not m.get("actual_finish") and m.get("status") != "On Track"

