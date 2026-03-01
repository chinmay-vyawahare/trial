from sqlalchemy.orm import Session
from .queries import build_gantt_query
from .logic import compute_milestones_for_site

def get_all_sites_gantt(
    db: Session,
    region: str = None,
    market: str = None,
    site_id: str = None,
    vendor: str = None,
    limit: int = None,
    offset: int = None,
):
    query, params = build_gantt_query(
        region=region,
        market=market,
        site_id=site_id,
        vendor=vendor,
        limit=limit,
        offset=offset,
    )
    result = db.execute(query, params)
    rows = [dict(r._mapping) for r in result]

    sites = []
    total_count = 0
    count = 0
    if rows:
        total_count = rows[0]["total_count"]
        count = len(rows)

    for row in rows:
        milestones, forecasted_cx_start = compute_milestones_for_site(row)
        if not milestones:
            continue

        total = len(milestones)
        on_track_count = sum(1 for m in milestones if m["status"] == "On Track")
        in_progress_count = sum(1 for m in milestones if m["status"] == "In Progress")
        delayed_count = sum(1 for m in milestones if m["status"] == "Delayed")

        max_delay = max((m.get("delay_days", 0) or 0) for m in milestones)

        if max_delay >= 15:
            overall = "CRITICAL"
        elif max_delay >= 8:
            overall = "HIGH RISK"
        elif max_delay >= 1:
            overall = "DELAYED"
        elif (on_track_count + in_progress_count) > 0:
            overall = "IN PROGRESS"
        else:
            overall = "PENDING"

        sites.append(
            {
                "vendor_name": row.get("a_gc_assignment") or "",
                "site_id": row["site_id"],
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "market": row["market"],
                "region": row.get("region") or "",
                "forecasted_cx_start_date": (
                    str(forecasted_cx_start) if forecasted_cx_start else None
                ),
                "milestones": milestones,
                "overall_status": overall,
                "milestone_status_summary": {
                    "total": total,
                    "on_track": on_track_count,
                    "in_progress": in_progress_count,
                    "delayed": delayed_count,
                },
            }
        )

    return sites, total_count, count

def get_dashboard_summary(
    db: Session,
    region: str = None,
    market: str = None,
    vendor: str = None,
    overall_status: str = None,
):
    sites, _, __ = get_all_sites_gantt(db, region=region, market=market, vendor=vendor)

    if overall_status:
        # overall_status in data is uppercase like "CRITICAL", "DELAYED", etc.
        sites = [
            s
            for s in sites
            if s["overall_status"].upper() == overall_status.upper().replace("_", " ")
        ]

    total = len(sites)
    in_progress = sum(1 for s in sites if s["overall_status"] == "IN PROGRESS")
    pending = sum(1 for s in sites if s["overall_status"] == "PENDING")
    delayed = sum(
        1 for s in sites if s["overall_status"] in ("DELAYED", "HIGH RISK", "CRITICAL")
    )
    critical = sum(1 for s in sites if s["overall_status"] == "CRITICAL")
    on_track = sum(1 for s in sites if s["overall_status"] == "IN PROGRESS")

    market_map = {}
    for s in sites:
        m = s["market"] or "Unknown"
        if m not in market_map:
            market_map[m] = {
                "market": m,
                "total": 0,
                "in_progress": 0,
                "delayed": 0,
                "pending": 0,
            }
        market_map[m]["total"] += 1
        if s["overall_status"] == "IN PROGRESS":
            market_map[m]["in_progress"] += 1
        elif s["overall_status"] in ("DELAYED", "HIGH RISK", "CRITICAL"):
            market_map[m]["delayed"] += 1
        else:
            market_map[m]["pending"] += 1

    vendor_map = {}
    for s in sites:
        gc = s["vendor_name"] or "Unassigned"
        if gc not in vendor_map:
            vendor_map[gc] = {
                "vendor": gc,
                "active_sites": 0,
                "delayed": 0,
            }
        vendor_map[gc]["active_sites"] += 1
        if s["overall_status"] in ("DELAYED", "HIGH RISK", "CRITICAL"):
            vendor_map[gc]["delayed"] += 1

    return {
        "total_sites": total,
        "in_progress_sites": in_progress,
        "pending_sites": pending,
        "delayed_sites": delayed,
        "critical_sites": critical,
        "on_track_sites": on_track,
        "markets": list(market_map.values()),
        "vendor_summary": list(vendor_map.values()),
    }
