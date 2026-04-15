import math
from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy.orm import Session
from .queries import build_gantt_query, build_light_cx_query
from .logic import compute_milestones_for_site, compute_milestones_for_site_actual, compute_overall_status, compute_status, _get_actual_date, _match_pct_threshold, get_milestone_range_for_status, is_site_blocked
from .milestones import get_milestones, get_all_actual_columns, get_planned_start_column, get_milestone_thresholds, get_overall_thresholds, apply_user_expected_days, get_history_expected_days_overrides, get_history_expected_days_by_user, save_user_history_expected_days
from .utils import parse_date

def _apply_uploaded_overrides(sites: list[dict], config_db: Session, user_id: str) -> list[dict]:
    """
    Override forecasted_cx_start_date with user-uploaded data from macro_uploaded_data.

    Matches by (site_id, project_id). If a match is found and the uploaded row
    has a valid pj_p_4225_construction_start_finish date, it replaces the forecasted date.
    """
    from app.models.prerequisite import MacroUploadedData

    rows = (
        config_db.query(MacroUploadedData)
        .filter(MacroUploadedData.uploaded_by == user_id)
        .all()
    )
    if not rows:
        return sites

    # Build lookup: (site_id, project_id) -> uploaded date
    upload_lookup: dict[tuple[str, str], date] = {}
    for r in rows:
        if r.pj_p_4225_construction_start_finish:
            d = r.pj_p_4225_construction_start_finish
            key = (r.site_id.strip(), (r.project_id or "").strip())
            upload_lookup[key] = d.date() if hasattr(d, "date") else d

    if not upload_lookup:
        return sites

    for site in sites:
        site_id = (site.get("site_id") or "").strip()
        project_id = (site.get("project_id") or "").strip()
        key = (site_id, project_id)
        if key in upload_lookup:
            uploaded_date = upload_lookup[key]
            site["forecasted_cx_start_date"] = str(uploaded_date)
            site["forecasted_cx_source"] = "uploaded"

    return sites



def _apply_pace_constraint(
    sites: list[dict],
    config_db: Session,
    pace_constraint_flag: bool,
    user_id: str,
    strict_pace_apply: bool = False,
) -> list[dict]:
    """
    Apply pace constraints to sites for a specific user_id.

    When strict_pace_apply=False (default — cascading mode):
        1. Collect all geo-matching sites in that week.
        2. Sort by forecasted_cx_start_date (earliest first) — keep up to max_sites.
        3. Push excess sites to the next week by advancing their forecasted_cx_start_date.
        4. Repeat for subsequent weeks until no week overflows.

    When strict_pace_apply=True (strict mode):
        1. For each week, keep up to max_sites (earliest forecast first).
        2. Exclude the rest — mark them but do NOT move them to the next week.
    """
    from app.models.prerequisite import PaceConstraint

    if (not pace_constraint_flag and not strict_pace_apply) or not user_id:
        return sites

    constraints = config_db.query(PaceConstraint).filter(
        PaceConstraint.user_id == user_id
    ).all()

    if not constraints:
        return sites

    # --------------------------------
    # Preprocess sites: parse forecast date & normalize geo
    # --------------------------------
    for site in sites:
        forecast = site.get("forecasted_cx_start_date")
        try:
            site["_forecast_date"] = date.fromisoformat(str(forecast)) if forecast else None
        except Exception:
            site["_forecast_date"] = None

        site["excluded_due_to_pace_constraint"] = False
        site.setdefault("note", "")

        site["_market"] = (site.get("market") or "").strip().lower()
        site["_area"] = (site.get("area") or "").strip().lower()
        site["_region"] = (site.get("region") or "").strip().lower()

    # --------------------------------
    # Helper: get Monday of a given date's ISO week
    # --------------------------------
    def week_monday(d: date) -> date:
        return d - timedelta(days=d.weekday())

    def next_week_start() -> date:
        today = date.today()
        return today - timedelta(days=today.weekday()) + timedelta(weeks=1)

    # --------------------------------
    # Process each constraint
    # --------------------------------
    for c in constraints:
        # Determine the starting week
        if getattr(c, "start_date", None):
            start_monday = week_monday(c.start_date.date())
        else:
            start_monday = next_week_start()

        c_market = (c.market or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_region = (c.region or "").strip().lower()
        max_sites = c.max_sites

        # Collect all geo-matching site indices with valid forecast dates
        # that fall on or after the constraint start week
        geo_indices: list[int] = []
        for idx, site in enumerate(sites):
            fd = site.get("_forecast_date")
            if not fd:
                continue
            if c_market and site["_market"] != c_market:
                continue
            if c_area and site["_area"] != c_area:
                continue
            if c_region and site["_region"] != c_region:
                continue
            if fd < start_monday:
                continue
            geo_indices.append(idx)

        if not geo_indices:
            continue

        # Group geo-matching sites by their ISO week Monday
        week_groups: dict[date, list[int]] = defaultdict(list)
        for idx in geo_indices:
            fd = sites[idx]["_forecast_date"]
            monday = week_monday(fd)
            week_groups[monday].append(idx)

        # Process weeks in chronological order
        processed_weeks = sorted(week_groups.keys())

        week_idx = 0
        while week_idx < len(processed_weeks):
            current_monday = processed_weeks[week_idx]
            indices_in_week = week_groups[current_monday]

            if len(indices_in_week) > max_sites:
                # ── Too many sites: overflow handling ──
                indices_in_week.sort(key=lambda i: sites[i]["_forecast_date"])
                keep = indices_in_week[:max_sites]
                overflow = indices_in_week[max_sites:]

                week_groups[current_monday] = keep

                if pace_constraint_flag:
                    # Cascading mode: push overflow to next week (takes priority when both flags are true)
                    next_monday = current_monday + timedelta(weeks=1)
                    for i in overflow:
                        sites[i]["excluded_due_to_pace_constraint"] = True
                        sites[i]["exclude_reason"] = "Excluded - Pace Constraint"

                        sites[i]["_forecast_date"] = next_monday
                        sites[i]["forecasted_cx_start_date"] = str(next_monday)

                        week_groups[next_monday].append(i)

                    if next_monday not in set(processed_weeks):
                        processed_weeks.append(next_monday)
                        processed_weeks.sort()

                elif strict_pace_apply:
                    # Strict mode: mark for removal (dropped from results entirely)
                    for i in overflow:
                        sites[i]["_remove"] = True

            elif len(indices_in_week) < max_sites and pace_constraint_flag:
                # ── Too few sites: pull earliest from future weeks ──
                needed = max_sites - len(indices_in_week)
                # Gather all sites from future weeks, sorted by forecast date
                future_candidates = []
                for future_monday in processed_weeks[week_idx + 1:]:
                    for i in week_groups[future_monday]:
                        future_candidates.append((i, sites[i]["_forecast_date"]))
                future_candidates.sort(key=lambda x: x[1])

                pulled = 0
                for i, _ in future_candidates:
                    if pulled >= needed:
                        break
                    # Remove from its current future week
                    for fm in processed_weeks[week_idx + 1:]:
                        if i in week_groups[fm]:
                            week_groups[fm].remove(i)
                            break

                    # Move site to current week
                    original_date = sites[i]["forecasted_cx_start_date"]
                    sites[i]["_forecast_date"] = current_monday
                    sites[i]["forecasted_cx_start_date"] = str(current_monday)
                    sites[i]["note"] = f"Pulled from {original_date} to fill pace constraint"
                    week_groups[current_monday].append(i)
                    pulled += 1

            week_idx += 1

    # --------------------------------
    # Final: remove strict-excluded sites, set flags & cleanup
    # --------------------------------
    if strict_pace_apply:
        sites = [s for s in sites if not s.get("_remove")]

    for site in sites:
        if not site.get("excluded_due_to_pace_constraint"):
            site["excluded_due_to_pace_constraint"] = False

        site.pop("_forecast_date", None)
        site.pop("_market", None)
        site.pop("_area", None)
        site.pop("_region", None)
        site.pop("_remove", None)

    return sites


def _apply_vendor_capacity(sites: list[dict], db: Session) -> list[dict]:
    """
    Apply vendor capacity constraints from public.gc_capacity_market_trial table.

    For each vendor+market+day combination, if the vendor has more sites starting
    on that day than their day_wise_gc_capacity, keep the first N and mark the
    rest as excluded_due_to_crew_shortage=True.
    """
    from app.models.prerequisite import GcCapacityMarketTrial

    # Load all capacity rules from public schema (pre-populated, read-only)
    capacity_rows = db.query(GcCapacityMarketTrial).all()
    if not capacity_rows:
        return sites

    # Build lookup: (gc_company_lower, market_lower) -> day_wise_capacity
    cap_lookup = {}
    for r in capacity_rows:
        key = (r.gc_company.strip().lower(), r.market.strip().lower())
        cap_lookup[key] = r.day_wise_gc_capacity

    # Group sites by (vendor, market, forecast_date)
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for idx, site in enumerate(sites):
        vendor_name = (site.get("vendor_name") or "").strip().lower()
        market_name = (site.get("market") or "").strip().lower()
        forecast_date = site.get("forecasted_cx_start_date") or ""
        if vendor_name and market_name and forecast_date:
            groups[(vendor_name, market_name, forecast_date)].append(idx)

    # For each (vendor, market, day) group, check capacity
    excluded_indices = set()
    for (vendor_key, market_key, _), indices in groups.items():
        capacity = cap_lookup.get((vendor_key, market_key))
        if capacity is None or len(indices) <= capacity:
            continue

        # More sites than capacity on this day — exclude excess
        for i in indices[capacity:]:
            excluded_indices.add(i)

    # Tag sites
    for idx, site in enumerate(sites):
        if idx in excluded_indices:
            site["excluded_due_to_crew_shortage"] = True
            site["exclude_reason"] = "Excluded - Crew Shortage"
        else:
            site["excluded_due_to_crew_shortage"] = False

    return sites


def get_all_sites_gantt(
    db: Session,
    config_db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    user_back_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
    strict_pace_apply: bool = False,
    view_type: str = "forecast",
):
    # Load milestone config from config DB
    milestones_config = get_milestones(config_db)
    milestone_columns = get_all_actual_columns(milestones_config)
    planned_start_col = get_planned_start_column(config_db)
    ms_thresholds = get_milestone_thresholds(config_db)

    # Lazy-load user back_days overrides for actual view
    if view_type == "actual" and user_id and user_back_days_overrides is None:
        from .milestones import get_user_back_days_overrides
        user_back_days_overrides = get_user_back_days_overrides(config_db, user_id)

    # For actual view, also need pj_p_4225_construction_start_finish column
    if view_type == "actual" and "pj_p_4225_construction_start_finish" not in milestone_columns:
        milestone_columns = list(milestone_columns) + ["pj_p_4225_construction_start_finish"]

    # Actual view uses a two-phase flow (light cx → constraints → heavy fetch)
    # so milestone dates are computed against the settled (pace-adjusted) CX.
    if view_type == "actual":
        return _run_actual_two_phase(
            db=db, config_db=config_db,
            milestones_config=milestones_config,
            planned_start_col=planned_start_col,
            milestone_columns=milestone_columns,
            ms_thresholds=ms_thresholds,
            region=region, market=market, site_id=site_id,
            vendor=vendor, area=area,
            plan_type_include=plan_type_include,
            regional_dev_initiatives=regional_dev_initiatives,
            limit=limit, offset=offset,
            skipped_keys=skipped_keys,
            user_expected_days_overrides=user_expected_days_overrides,
            user_back_days_overrides=user_back_days_overrides,
            consider_vendor_capacity=consider_vendor_capacity,
            pace_constraint_flag=pace_constraint_flag,
            strict_pace_apply=strict_pace_apply,
            user_id=user_id,
        )

    # Query staging data from staging DB
    query, params = build_gantt_query(
        milestone_columns=milestone_columns,
        planned_start_column=planned_start_col,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
        view_type=view_type
    )
    result = db.execute(query, params)
    rows = [dict(r._mapping) for r in result]

    sites = []
    total_count = 0
    count = 0
    if rows:
        total_count = rows[0]["total_count"]
        count = len(rows)

    # Forecast-only path beyond this point — actual view returned above.
    today = date.today()

    for row in rows:
        milestones, forecasted_cx_start = compute_milestones_for_site(
            row, config_db, skipped_keys=skipped_keys,
            user_expected_days_overrides=user_expected_days_overrides,
        )
        if not milestones:
            continue

        countable = [m for m in milestones if not m.get("is_virtual", False)]
        total = len(countable)
        on_track_count = sum(1 for m in countable if m["status"] == "On Track")
        in_progress_count = sum(1 for m in countable if m["status"] == "In Progress")
        delayed_count = sum(1 for m in countable if m["status"] == "Delayed")

        blocked = is_site_blocked(row)
        if blocked:
            overall = "Blocked"
            on_track_pct = 0
        else:
            overall = compute_overall_status(on_track_count, total, ms_thresholds)
            on_track_pct = round((on_track_count / total * 100), 2) if total > 0 else 0

        # Forecast reschedule: if cx is in the past, bump to next week and annotate.
        note = None
        if forecasted_cx_start and forecasted_cx_start < today:
            missing = [m for m in countable if not m.get("actual_finish")]
            if not missing:
                forecasted_cx_start = today + timedelta(days=7)
                note = "Ready for schedule"
            else:
                missing_sorted = sorted(missing, key=lambda m: m.get("sort_order", 999))
                blocker = missing_sorted[0]
                delay_days = (today - forecasted_cx_start).days
                forecasted_cx_start = today + timedelta(days=7)
                note = f"Delayed due to {blocker['name']} by {delay_days} days"

        site_dict = {
            "vendor_name": row.get("construction_gc") or "",
            "site_id": row["s_site_id"],
            "project_id": row["pj_project_id"],
            "project_name": row["pj_project_name"],
            "market": row["m_market"],
            "area": row.get("m_area") or "",
            "region": row.get("region") or "",
            "delay_comments": row.get("pj_construction_start_delay_comments") or "",
            "delay_code": row.get("pj_construction_complete_delay_code") or "",
            "forecasted_cx_start_date": (
                str(forecasted_cx_start) if forecasted_cx_start else None
            ),
            "note": note,
            "milestones": [
                {k: v for k, v in m.items() if k != "is_virtual"}
                for m in milestones
            ],
            "overall_status": overall,
            "on_track_pct": on_track_pct,
            "milestone_status_summary": {
                "total": total,
                "on_track": on_track_count,
                "in_progress": in_progress_count,
                "delayed": delayed_count,
            },
        }

        sites.append(site_dict)

    # Apply vendor capacity constraints if requested
    if consider_vendor_capacity:
        sites = _apply_vendor_capacity(sites, db)
    else:
        for site in sites:
            site["excluded_due_to_crew_shortage"] = False

    # Apply pace constraints for user if enabled
    if (pace_constraint_flag or strict_pace_apply) and user_id:
        sites = _apply_pace_constraint(sites, config_db, pace_constraint_flag, user_id, strict_pace_apply=strict_pace_apply)
    else:
        for site in sites:
            site["excluded_due_to_pace_constraint"] = False
            
        # Override forecasted_cx_start_date from user-uploaded data if available
    if user_id:
        sites = _apply_uploaded_overrides(sites, config_db, user_id)

    # Sort by forecasted_cx_start_date descending (latest first, nulls at bottom)
    sites.sort(
        key=lambda s: s.get("forecasted_cx_start_date") or "",
        reverse=True,
    )

    return sites, total_count, count


def _run_actual_two_phase(
    *,
    db: Session,
    config_db: Session,
    milestones_config: list,
    planned_start_col: str,
    milestone_columns: list[str],
    ms_thresholds: list,
    region, market, site_id, vendor, area,
    plan_type_include, regional_dev_initiatives,
    limit, offset,
    skipped_keys,
    user_expected_days_overrides,
    user_back_days_overrides,
    consider_vendor_capacity,
    pace_constraint_flag,
    strict_pace_apply,
    user_id,
):
    """
    Two-phase flow for view_type="actual":

      1. Light query → (site_id, vendor, market, area, region, forecasted_cx)
      2. Apply vendor capacity + pace constraint on the light list (these
         shift `forecasted_cx_start_date` for overflow sites).
      3. Sort + paginate the settled list.
      4. Heavy query restricted to the paginated site_ids.
      5. Compute milestones per site with cx_override = settled CX.

    This ensures milestone planned_finish / status / delay_days are always
    consistent with the pace-adjusted CX, and avoids running the expensive
    milestone walk for sites that won't be displayed.
    """
    # --- Stage 1: light query ---
    light_q, light_params = build_light_cx_query(
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
    )
    light_rows = db.execute(light_q, light_params).fetchall()

    light_sites: list[dict] = []
    for r in light_rows:
        m = r._mapping
        light_sites.append({
            "site_id": m["s_site_id"],
            "project_id": m.get("pj_project_id") or "",
            "vendor_name": m.get("vendor_name") or "",
            "market": m.get("market") or "",
            "area": m.get("area") or "",
            "region": m.get("region") or "",
            "forecasted_cx_start_date": (
                str(m["forecasted_cx_start_date"]) if m.get("forecasted_cx_start_date") else None
            ),
        })

    # --- Stage 2: constraints ---
    if consider_vendor_capacity:
        light_sites = _apply_vendor_capacity(light_sites, db)
    else:
        for s in light_sites:
            s["excluded_due_to_crew_shortage"] = False

    if (pace_constraint_flag or strict_pace_apply) and user_id:
        light_sites = _apply_pace_constraint(
            light_sites, config_db, pace_constraint_flag, user_id,
            strict_pace_apply=strict_pace_apply,
        )
    else:
        for s in light_sites:
            s["excluded_due_to_pace_constraint"] = False

    if user_id:
        light_sites = _apply_uploaded_overrides(light_sites, config_db, user_id)

    total_count = len(light_sites)

    # --- Stage 3: sort + paginate ---
    light_sites.sort(
        key=lambda s: s.get("forecasted_cx_start_date") or "",
        reverse=True,
    )
    start = offset or 0
    end = start + limit if limit else len(light_sites)
    page = light_sites[start:end]

    page_ids = [s["site_id"] for s in page]
    if not page_ids:
        return [], total_count, 0

    # --- Stage 4: heavy query restricted to page ---
    heavy_q, heavy_params = build_gantt_query(
        milestone_columns=milestone_columns,
        planned_start_column=planned_start_col,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        view_type="actual",
        site_id_filter=page_ids,
    )
    heavy_rows = db.execute(heavy_q, heavy_params)
    row_by_id = {dict(r._mapping)["s_site_id"]: dict(r._mapping) for r in heavy_rows}

    today = date.today()

    # Load user-uploaded per-milestone actuals (keyed by site_id+project_id).
    # When a site+project has an uploaded payload, those milestone values
    # take precedence over the staging-DB columns during compute.
    uploaded_actuals_map: dict[tuple[str, str], dict] = {}
    if user_id:
        from app.services.macro_milestone_upload import get_user_milestone_actuals_map
        uploaded_actuals_map = get_user_milestone_actuals_map(config_db, user_id)

    # --- Stage 5: milestone compute per page site against SETTLED cx ---
    sites_out: list[dict] = []
    for light in page:
        row = row_by_id.get(light["site_id"])
        if row is None:
            continue

        settled_cx = parse_date(light["forecasted_cx_start_date"])
        if settled_cx is None:
            continue

        site_actual_overrides = uploaded_actuals_map.get(
            ((row.get("s_site_id") or "").strip(), (row.get("pj_project_id") or "").strip())
        )

        milestones, forecasted_cx_start = compute_milestones_for_site_actual(
            row, config_db,
            skipped_keys=skipped_keys,
            user_expected_days_overrides=user_expected_days_overrides,
            user_back_days_overrides=user_back_days_overrides,
            cx_override=settled_cx,
            actual_overrides=site_actual_overrides,
        )
        if not milestones:
            continue

        countable = [m for m in milestones if not m.get("is_virtual", False)]
        total = len(countable)
        on_track_count = sum(1 for m in countable if m["status"] == "On Track")
        in_progress_count = sum(1 for m in countable if m["status"] == "In Progress")
        delayed_count = sum(1 for m in countable if m["status"] == "Delayed")

        blocked = is_site_blocked(row)
        if blocked:
            overall = "Blocked"
            on_track_pct = 0
        else:
            overall = compute_overall_status(on_track_count, total, ms_thresholds)
            on_track_pct = round((on_track_count / total * 100), 2) if total > 0 else 0

        # Reschedule suggestion (actual view) — only when the forecasted CX is
        # in the future AND today + remaining-blocker days would push past it.
        # If the forecasted date is already past, the site is already late;
        # no forward-looking suggestion is useful.
        suggested_forecast_cx_start = None
        suggested_comment = None
        if settled_cx and settled_cx > today:
            missing = [m for m in countable if not m.get("actual_finish")]
            if missing:
                blocker = max(missing, key=lambda m: m.get("expected_days", 0))
                blocker_expected = blocker.get("expected_days", 0)
                temp = today + timedelta(days=blocker_expected)
                if temp > settled_cx:
                    suggested_forecast_cx_start = temp
                    suggested_comment = f"Suggested {suggested_forecast_cx_start} due to delay in {blocker['name']}"

        site_dict = {
            "vendor_name": row.get("construction_gc") or "",
            "site_id": row["s_site_id"],
            "project_id": row["pj_project_id"],
            "project_name": row["pj_project_name"],
            "market": row["m_market"],
            "area": row.get("m_area") or "",
            "region": row.get("region") or "",
            "delay_comments": row.get("pj_construction_start_delay_comments") or "",
            "delay_code": row.get("pj_construction_complete_delay_code") or "",
            "forecasted_cx_start_date": light["forecasted_cx_start_date"],
            "note": light.get("note"),
            "milestones": [
                {k: v for k, v in m.items() if k != "is_virtual"}
                for m in milestones
            ],
            "overall_status": overall,
            "on_track_pct": on_track_pct,
            "milestone_status_summary": {
                "total": total,
                "on_track": on_track_count,
                "in_progress": in_progress_count,
                "delayed": delayed_count,
            },
            "excluded_due_to_crew_shortage": bool(light.get("excluded_due_to_crew_shortage")),
            "excluded_due_to_pace_constraint": bool(light.get("excluded_due_to_pace_constraint")),
            "suggested_forecast_cx_start": (
                str(suggested_forecast_cx_start) if suggested_forecast_cx_start else None
            ),
            "suggested_comment": suggested_comment,
        }
        if "exclude_reason" in light:
            site_dict["exclude_reason"] = light["exclude_reason"]

        sites_out.append(site_dict)

    return sites_out, total_count, len(sites_out)


def _site_status(row, milestones_config, planned_start_col, ms_thresholds, skipped_keys, user_expected_days_overrides=None):
    """Compute overall status for one row — only dates, no full milestone dicts."""
    # Blocked sites get their own status — excluded from on_track/in_progress/critical counts
    if is_site_blocked(row):
        return "BLOCKED"

    origin_date = parse_date(row.get(planned_start_col))
    if origin_date is None:
        return None

    today = date.today()
    skipped = skipped_keys or set()
    overrides = user_expected_days_overrides or {}
    expected_by_key = {
        m["key"]: overrides.get(m["key"], m["expected_days"])
        for m in milestones_config
    }

    # Compute planned finish dates
    dates = {}
    for ms in milestones_config:
        key = ms["key"]
        dep = ms["depends_on"]
        gap = ms.get("start_gap_days", 1)

        if key in skipped:
            expected = 0
        elif dep is not None and isinstance(dep, list) and len(dep) > 1:
            expected = max(expected_by_key.get(d, 0) for d in dep)
        else:
            expected = expected_by_key.get(key, ms["expected_days"])

        if dep is None:
            pf = origin_date + timedelta(days=expected) if expected > 0 else origin_date
            dates[key] = pf
            continue

        dep_list = dep if isinstance(dep, list) else [dep]
        dep_finishes = [dates[d] for d in dep_list if d in dates]
        if not dep_finishes:
            continue
        ps = max(dep_finishes) + timedelta(days=gap)
        dates[key] = ps + timedelta(days=expected)

    # Count on-track milestones (exclude user-skipped from counting entirely)
    on_track = 0
    total = 0
    for ms in milestones_config:
        key = ms["key"]
        if key not in dates:
            continue

        if key in skipped:
            continue  # exclude skipped milestones from counting

        total += 1

        actual, is_text, text_val, skip_flag = _get_actual_date(row, ms)
        if skip_flag:
            on_track += 1
            continue

        status, _ = compute_status(actual, dates[key], today, is_text, text_val)
        if status == "On Track":
            on_track += 1

    if total == 0:
        return None
    return compute_overall_status(on_track, total, ms_thresholds)


def _normalize_geo_filter(value) -> list[str]:
    """Normalize a geo filter value (str, list, or None) to a list of lowercase strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip().lower()]
    return [v.strip().lower() for v in value if v]


def _get_pace_constraint(config_db: Session, user_id: str | None, region=None, area=None, market=None) -> list[dict]:
    """
    Fetch pace constraints for a user that match the geo filters.

    Returns a list of constraint dicts with region, area, market, max_sites.
    """
    if not user_id:
        return []

    from app.models.prerequisite import PaceConstraint

    constraints = (
        config_db.query(PaceConstraint)
        .filter(PaceConstraint.user_id == user_id)
        .all()
    )
    if not constraints:
        return []

    f_regions = _normalize_geo_filter(region)
    f_areas = _normalize_geo_filter(area)
    f_markets = _normalize_geo_filter(market)

    result = []
    for c in constraints:
        c_region = (c.region or "").strip().lower()
        c_area = (c.area or "").strip().lower()
        c_market = (c.market or "").strip().lower()

        # Match: constraint geo must align with the filter geo
        if c_region:
            if f_regions and c_region not in f_regions:
                continue
        if c_area:
            if f_areas and c_area not in f_areas:
                continue
        if c_market:
            if f_markets and c_market not in f_markets:
                continue

        result.append({
            "region": c.region,
            "area": c.area,
            "market": c.market,
            "max_sites": c.max_sites,
        })

    return result


def get_dashboard_summary(
    db: Session,
    config_db: Session,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    skipped_keys: set[str] | None = None,
    user_expected_days_overrides: dict[str, int] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    status: str | None = None,
    user_id: str | None = None,
    strict_pace_apply: bool = False,
    view_type: str = "forecast",
):
    """Dashboard summary using the same query and logic as the gantt chart."""
    sites, total_count, _ = get_all_sites_gantt(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=user_expected_days_overrides,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        strict_pace_apply=strict_pace_apply,
        user_id=user_id,
        view_type=view_type,
    )

    result = _get_pace_constraint(config_db, user_id, region=region, area=area, market=market)
    print(result,"Result")
    pace_max = sum(item.get("max_sites", 0) for item in (result or []))
    print(pace_max,"Pace Max")
    _empty_detail = {"site_count": 0, "total_milestones": 0, "on_track_milestones": 0, "in_progress_milestones": 0, "delayed_milestones": 0, "on_track_pct": 0, "in_progress_pct": 0, "delayed_pct": 0}
    _empty_threshold = {"min_pct": 0, "max_pct": None, "milestone_range": "0-0/0", "description": ""}
    empty = {
        "dashboard_status": "ON TRACK",
        "on_track_pct": 0,
        "total_sites": 0,
        "in_progress_sites": 0,
        "critical_sites": 0,
        "on_track_sites": 0,
        "blocked_sites": 0,
        "excluded_crew_shortage_sites": 0,
        "excluded_pace_constraint_sites": 0,
        "pace_constraint_max_sites": pace_max,
        "status_details": {
            "ON TRACK": {**_empty_detail, "threshold": {**_empty_threshold}},
            "IN PROGRESS": {**_empty_detail, "threshold": {**_empty_threshold}},
            "CRITICAL": {**_empty_detail, "threshold": {**_empty_threshold}},
            "Blocked": {**_empty_detail},
        },
    }
    
    if not sites:
        return empty

    # Pace constraint already applied inside get_all_sites_gantt — no need to reapply

    # Apply status filter if provided
    if status:
        sites = [s for s in sites if s.get("overall_status") == status]

    total = len(sites)
    if total == 0:
        return empty

    blocked = sum(1 for s in sites if s["overall_status"] == "Blocked")
    excluded_crew = sum(1 for s in sites if s.get("exclude_reason") == "Excluded - Crew Shortage")
    excluded_pace = sum(1 for s in sites if s.get("exclude_reason") == "Excluded - Pace Constraint")

    # Count statuses excluding blocked
    countable = [s for s in sites if s["overall_status"] not in ("Blocked")]
    on_track = sum(1 for s in countable if s["overall_status"] == "ON TRACK")
    in_progress = sum(1 for s in countable if s["overall_status"] == "IN PROGRESS")
    critical = sum(1 for s in countable if s["overall_status"] == "CRITICAL")

    non_blocked_total = len(countable)
    on_track_pct = (on_track / non_blocked_total * 100) if non_blocked_total > 0 else 0

    overall_thresholds = get_overall_thresholds(config_db)
    if overall_thresholds:
        dashboard_status, _ = _match_pct_threshold(on_track_pct, overall_thresholds)
    elif on_track_pct >= 60:
        dashboard_status = "ON TRACK"
    elif on_track_pct >= 30:
        dashboard_status = "IN PROGRESS"
    else:
        dashboard_status = "CRITICAL"

    # Build milestone-level detail per status category
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

    return {
        "dashboard_status": dashboard_status,
        "on_track_pct": round(on_track_pct, 2),
        "total_sites": total,
        "in_progress_sites": in_progress,
        "critical_sites": critical,
        "on_track_sites": on_track,
        "blocked_sites": blocked,
        "excluded_crew_shortage_sites": excluded_crew,
        "excluded_pace_constraint_sites": excluded_pace,
        "pace_constraint_max_sites": pace_max,
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
    }


def get_history_gantt(
    db: Session,
    config_db: Session,
    date_from: date,
    date_to: date,
    region: list[str] | None = None,
    market: list[str] | None = None,
    site_id: str = None,
    vendor: str = None,
    area: list[str] | None = None,
    plan_type_include: list[str] | None = None,
    regional_dev_initiatives: str | None = None,
    limit: int = None,
    offset: int = None,
    skipped_keys: set[str] | None = None,
    consider_vendor_capacity: bool = False,
    pace_constraint_flag: bool = False,
    user_id: str | None = None,
    strict_pace_apply: bool = False,
    view_type: str = "forecast",
):
    """
    Gantt chart using history-based SLA.

    Computes history_expected_days from the given date range, saves them
    per-user into user_history_expected_days, then runs the gantt
    logic using those values as expected_days overrides.
    """
    from app.services.sla_history import compute_history_expected_days
    from app.models.prerequisite import UserHistoryExpectedDays

    # Compute history-based duration from actual dates.
    # When view_type="actual" the function returns historical back_days
    # (cx_actual - ms_actual) under the same `history_expected_days` key.
    history_results = compute_history_expected_days(
        db, config_db, date_from, date_to,
        region=region, market=market, site_id=site_id,
        vendor=vendor, area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        view_type=view_type,
    )

    # Build overrides dict.
    # In forecast mode every milestone falls back to 0 when no history exists
    # (never fall back to defaults). In actual mode, only milestones with
    # computed back_days override; rest fall through to the persisted
    # MilestoneDefinition.back_days fast-path.
    is_actual = view_type == "actual"
    overrides: dict[str, int] = {}
    for item in history_results:
        computed = item["history_expected_days"]
        if is_actual:
            if computed is not None:
                overrides[item["milestone_key"]] = computed
        else:
            overrides[item["milestone_key"]] = computed if computed is not None else 0

    # Save per-user history values into the right column based on view_type.
    if user_id:
        save_user_history_expected_days(
            config_db, user_id, history_results, date_from, date_to,
            view_type=view_type,
        )

    # Get the latest updated_at timestamp for this user's history SLA
    from sqlalchemy import func as sa_func
    last_updated_row = None
    if user_id:
        last_updated_row = (
            config_db.query(sa_func.max(UserHistoryExpectedDays.updated_at))
            .filter(UserHistoryExpectedDays.user_id == user_id)
            .scalar()
        )
    sla_last_updated = str(last_updated_row) if last_updated_row else None

    # Reuse the standard gantt function with history overrides
    sites, total_count, count = get_all_sites_gantt(
        db=db,
        config_db=config_db,
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        area=area,
        plan_type_include=plan_type_include,
        regional_dev_initiatives=regional_dev_initiatives,
        limit=limit,
        offset=offset,
        skipped_keys=skipped_keys,
        user_expected_days_overrides=overrides if not is_actual else None,
        user_back_days_overrides=overrides if is_actual else None,
        consider_vendor_capacity=consider_vendor_capacity,
        pace_constraint_flag=pace_constraint_flag,
        user_id=user_id,
        strict_pace_apply=strict_pace_apply,
        view_type=view_type,
    )

    return sites, total_count, count, sla_last_updated
