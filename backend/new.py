    status_by_key = {m["key"]: m["status"] for m in milestones}
    # Build key→dependents map (who depends on me)
    dependents_map: Dict[str, List[str]] = {m["key"]: [] for m in milestones}
    for ms_cfg in milestones_config:
        dep = ms_cfg["depends_on"]
        if dep is None:
            continue
        dep_list = dep if isinstance(dep, list) else [dep]
        for d in dep_list:
            if d in dependents_map:
                dependents_map[d].append(ms_cfg["key"])

    for m in milestones:
        if m.get("is_virtual"):
            continue
        if m["status"] in ("Delayed", "In Progress"):
            # Check if any dependent milestone is On Track
            for dep_key in dependents_map.get(m["key"], []):
                if status_by_key.get(dep_key) == "On Track":
                    m["status"] = "On Track"
                    m["delay_days"] = 0
                    break
