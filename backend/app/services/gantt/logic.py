from datetime import date, timedelta
from typing import Optional, List, Dict
from .utils import parse_date
from .milestones import MILESTONES, PREREQ_TAILS, CX_START_OFFSET_DAYS


def compute_status(actual: Optional[date], pf: Optional[date], today: date, is_text_field=False, text_val=None):
    if is_text_field:
        val = text_val or ""
        if val.strip():
            return "On Track", 0
        return "In Progress", 0
    if actual is not None:
        delay = (actual - pf).days if pf else 0
        if delay <= 0:
            return "On Track", delay
        return "Delayed", delay
    if pf is not None:
        remaining = (pf - today).days
        if remaining >= 0:
            return "In Progress", 0
        return "Delayed", abs(remaining)
    return "In Progress", 0


def _get_actual_date(row: Dict, ms: Dict):
    """Extract the actual date/value for a milestone from the row."""
    key = ms["key"]
    is_text = ms.get("is_text", False)

    if key == "site_walk":
        a_manual = parse_date(row.get("a_site_walk_manual_raw"))
        a_drone = parse_date(row.get("a_site_walk_drone_raw"))
        if a_manual and a_drone:
            return min(a_manual, a_drone), False, None
        return a_manual or a_drone, False, None

    if key == "steel":
        return parse_date(row.get("a_steel_date_raw")), False, None

    if is_text:
        text_val = row.get(ms["actual_field"]) or ""
        return None, True, text_val

    return parse_date(row.get(ms["actual_field"])), False, None


def _compute_planned_dates(p_3710: date):
    """Compute planned start/finish for every milestone based on dependency chain."""
    dates = {}

    # 3710: origin
    dates["3710"] = {"ps": p_3710, "pf": p_3710}

    # Pre-NTP: starts at Entitlement, 2d
    ps = p_3710
    pf = ps + timedelta(days=2)
    dates["pre_ntp"] = {"ps": ps, "pf": pf}

    # Site Walk: after Pre-NTP, 7d
    ps = dates["pre_ntp"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=7)
    dates["site_walk"] = {"ps": ps, "pf": pf}

    # Ready for Scoping: after Site Walk, 3d
    ps = dates["site_walk"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=3)
    dates["1323"] = {"ps": ps, "pf": pf}

    # Scoping Validated: after Ready for Scoping, 7d
    ps = dates["1323"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=7)
    dates["1327"] = {"ps": ps, "pf": pf}

    # BOM in BAT: after Scoping Validated, 14d
    ps = dates["1327"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=14)
    dates["3850"] = {"ps": ps, "pf": pf}

    # BOM in AIMS: after BOM in BAT, 21d
    ps = dates["3850"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=21)
    dates["3875"] = {"ps": ps, "pf": pf}

    # Steel Received: after Scoping Validated, 14d
    ps = dates["1327"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=14)
    dates["steel"] = {"ps": ps, "pf": pf}

    # Material Pickup: after Steel, 5d
    ps = dates["steel"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=5)
    dates["3925"] = {"ps": ps, "pf": pf}

    # Quote: after Scoping Validated, 7d
    ps = dates["1327"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=7)
    dates["quote"] = {"ps": ps, "pf": pf}

    # CPO: after Quote, 14d
    ps = dates["quote"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=14)
    dates["cpo"] = {"ps": ps, "pf": pf}

    # SPO: after CPO, 5d
    ps = dates["cpo"]["pf"] + timedelta(days=1)
    pf = ps + timedelta(days=5)
    dates["spo"] = {"ps": ps, "pf": pf}

    # Access Confirmation: 7d after Scoping Validated, 7d
    ps = dates["1327"]["pf"] + timedelta(days=7)
    pf = ps + timedelta(days=7)
    dates["access"] = {"ps": ps, "pf": pf}

    # NTP: 14d after Scoping Validated, 7d
    ps = dates["1327"]["pf"] + timedelta(days=14)
    pf = ps + timedelta(days=7)
    dates["ntp"] = {"ps": ps, "pf": pf}

    return dates


def compute_milestones_for_site(row: Dict) -> tuple[List[Dict], Optional[date]]:
    today = date.today()

    p_3710 = parse_date(row.get("p_3710_raw"))
    if p_3710 is None:
        return [], None

    # Compute all planned dates
    dates = _compute_planned_dates(p_3710)

    # Steel status from DB
    a_steel_status = row.get("a_steel_status") or ""
    steel_status_str = a_steel_status.strip() if a_steel_status else ""

    milestones = []

    for ms in MILESTONES:
        key = ms["key"]
        ps = dates[key]["ps"]
        pf = dates[key]["pf"]
        is_text = ms.get("is_text", False)
        actual, is_text_override, text_val = _get_actual_date(row, ms)

        # Build depends_on display string
        dep = ms["depends_on"]
        if dep is None:
            depends_on_str = None
        elif isinstance(dep, list):
            dep_names = []
            for d in dep:
                dep_ms = next((m for m in MILESTONES if m["key"] == d), None)
                dep_names.append(dep_ms["name"] if dep_ms else d)
            depends_on_str = " / ".join(dep_names)
        else:
            dep_ms = next((m for m in MILESTONES if m["key"] == dep), None)
            depends_on_str = dep_ms["name"] if dep_ms else dep

        # Steel has special handling based on status
        if key == "steel":
            if steel_status_str in ("N", "Not Applicable", "") or steel_status_str is None:
                milestones.append({
                    "key": key,
                    "name": ms["name"],
                    "sort_order": ms["sort_order"],
                    "expected_days": ms["expected_days"],
                    "depends_on": depends_on_str,
                    "planned_start": str(ps),
                    "planned_finish": str(pf),
                    "actual_finish": str(actual) if actual else None,
                    "days_since": None,
                    "days_remaining": None,
                    "delay_days": 0,
                    "status": "On Track",
                })
                continue
            elif steel_status_str == "A":
                pass  # use actual date as-is
            else:
                actual = None  # P or unknown → pending

        # Standard milestone processing
        use_text = is_text or is_text_override
        status, delay = compute_status(actual, pf, today, use_text, text_val)
        days_since = (today - actual).days if actual else None
        days_remaining = (pf - today).days if (actual is None and pf) else None

        milestones.append({
            "key": key,
            "name": ms["name"],
            "sort_order": ms["sort_order"],
            "expected_days": ms["expected_days"],
            "depends_on": depends_on_str,
            "planned_start": str(ps) if ps else None,
            "planned_finish": str(pf) if pf else None,
            "actual_finish": (
                str(actual) if actual
                else (text_val if use_text and text_val else None)
            ),
            "days_since": days_since,
            "days_remaining": days_remaining,
            "delay_days": delay,
            "status": status,
        })

    # ----------------------------------------------------------------
    # All Prerequisites Complete
    # ----------------------------------------------------------------
    tail_dates = []
    for tail in PREREQ_TAILS:
        pf_tail = dates[tail["key"]]["pf"]
        tail_dates.append(pf_tail + timedelta(days=tail["offset_days"]))

    all_prereq_complete = max(tail_dates)

    milestones.append({
        "key": "all_prereq",
        "name": "All Prerequisites Complete",
        "sort_order": 15,
        "expected_days": 0,
        "depends_on": "All path tails",
        "planned_start": str(all_prereq_complete),
        "planned_finish": str(all_prereq_complete),
        "actual_finish": None,
        "days_since": None,
        "days_remaining": (all_prereq_complete - today).days if all_prereq_complete else None,
        "delay_days": 0,
        "status": "In Progress" if all_prereq_complete >= today else "Delayed",
    })

    # ----------------------------------------------------------------
    # Forecasted CX Start
    # ----------------------------------------------------------------
    forecasted_cx_start = all_prereq_complete + timedelta(days=CX_START_OFFSET_DAYS)

    return milestones, forecasted_cx_start
