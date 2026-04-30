## 1. The 12 AHLOA Milestones (loaded from the database)

Every AHLOA site is graded against the same fixed catalog of 12 milestones, stored in `ahloa_milestone_definitions` and `ahloa_milestone_columns`. Order, owners, durations, and column mappings are admin‑configurable; what's listed below is the **current production configuration**.

| # | Milestone | Owner | Phase | Days **before** CX |
|---|---|---|---|---|
| 1 | CPO For Site | TMO | Pre‑CX | 0 (text presence) |
| 2 | BOM Ready (MS 3850) | CM | Material | 42 |
| 3 | BOM Material in MSL (MS 3875) | TMO | Material | 10 |
| 4 | Material Pickup by GC (MS 3925) | GC | Material | 7 |
| 5 | LL NTP Ready (MS 4000) | TMO | NTP | 28 (text presence) |
| 6 | Overall NTP Ready (MS 4075) | TMO | NTP | 28 |
| 7 | Final NTP Ready (MS 4100) | PDM | NTP | 28 |
| 8 | SPO to GC for CX | PROJECT‑OPS | SPO | 42 |
| 9 | Crane | GC | Crane Readiness | 14 (status `Yes`/`No` = on track) |
| 10 | Talon Session for Scoping | SE‑CoE | Scoping | 14 |
| 11 | Talon Session for SCOP | SE‑CoE | SCOP | 14 |
| 12 | Planned Activity Upload in NAS | GC | Outage Readiness | 7 (from external NAS table) |

Two milestones are **text‑presence checks** (CPO and LL NTP Ready) — populated means On Track, blank means Delayed. One is a **status check** (Crane) — values `Yes` or `No` count as On Track, blank counts as Delayed. One reads from a **separate table** (NAS) — joined by site_id with project category `AHLOB` from `stg_nas_planned_outage_activity`.

---

## 2. Site Eligibility — which sites become "AHLOA" in the first place

A row from the staging table only enters the AHLOA Gantt if it satisfies **all four** filters:

| Filter | Meaning |
|---|---|
| `pj_hard_cost_vendor_assignment_po ILIKE '%NOKIA%'` | Nokia‑vendored sites only |
| `por_release_version = 'Radio Upgrade NR'` | Radio upgrade scope |
| `por_plan_added_date > '2025-03-28'` | New plan added after this cutoff |
| `pj_a_4225_construction_start_finish IS NULL` | Construction has not actually started yet |

Sites whose computed CX Start falls in the past with no fallback are also dropped (see Section 3).

---

## 3. CX Start Formula — the Anchor Everything Hangs Off

For every AHLOA site we compute a single anchor date:

```
CX Start = max(pj_p_3710_ran_entitlement_complete_finish,
               pj_p_4075_construction_ntp_submitted_to_gc_finish) + 50 days
```

If that result is in the past, the system falls back to `pj_p_4225_construction_start_finish` when it's available (forecasted source becomes `"p_4225_fallback"`). If neither is usable and the formula is still in the past, the site is dropped entirely. There is **no** forward dependency walk and **no** chain of milestone offsets — every milestone simply hangs off this one CX date.

---

## 4. Status Vocabulary

There are only **four** site‑level statuses and only **three** milestone‑level statuses.

### Per‑Milestone Status

| Status | Meaning |
|---|---|
| **On Track** | Date milestone: actual is on or before its expected date. Text milestone: field is populated. Status milestone: value is `Yes` or `No`. |
| **In Progress** | No actual yet, expected date is still in the future, work is open. |
| **Delayed** | Either (a) actual is after expected, (b) expected has passed with no actual, or (c) text/status field is blank. |

### Per‑Site Overall Status (the colored badge)

The overall site status is computed from the **on‑track percentage** = `on_track_milestones ÷ total_countable_milestones × 100`, matched against `ahloa_constraint_thresholds`:

| Site Status | On‑Track % range | Color |
|---|---|---|
| **READY** | 93 % – 100 % | green |
| **ON TRACK** | 65 % – 92.99 % | green |
| **IN PROGRESS** | 30 % – 64.99 % | orange |
| **CRITICAL** | 0 % – 29.99 % | red |
| **BLOCKED** | (overrides everything — see below) | grey/red |

### When is a site BLOCKED?

A site is forced to **Blocked** — regardless of milestone status — if **either** of these is populated on the staging row:

- `pj_construction_complete_delay_code` (any code) except 'no delay'.

Blocked sites are excluded from the percentage base of every other category so they don't dilute the dashboard roll‑up.

### Dashboard Roll‑Up

The dashboard re‑runs the same percentage calculation, but at the **portfolio** level — `on_track_sites ÷ non_blocked_sites × 100` — matched against the **overall** thresholds:

| Dashboard Status | % of sites On Track |
|---|---|
| ON TRACK | ≥ 60 % |
| IN PROGRESS | 30 % – 59.99 % |
| CRITICAL | 0 % – 29.99 % |

Blocked sites and sites excluded by capacity / pace constraints are reported as separate counters and are **not** counted in the percentage base.

---

## 5. How Each Milestone is Graded

For a date milestone, the **expected date = CX Start − the milestone's `expected_days`**. So with CX = 2026‑06‑06 and Material Pickup's offset of 7 days, the expected date is 2026‑05‑30. The actual date is then compared:

- Actual date ≤ expected date → **On Track**.
- Actual date > expected date → **Delayed** (with the gap reported in days).
- No actual date and expected is still in the future → **In Progress**.
- No actual date and expected has already passed → **Delayed**.

Text milestones (CPO, LL NTP Ready) are On Track if the field is populated, Delayed if blank. The Crane status milestone is On Track if its value is `Yes` or `No`, Delayed otherwise. The NAS Upload milestone reads from the external `stg_nas_planned_outage_activity` table filtered by `nas_project_category = 'AHLOB'` and joined by site_id.

## 6. Pace Constraint, Vendor Capacity, Skip & Unskip — Gantt Logic Detail

Four of the most user‑visible levers reshape the Gantt output. Each is described below in plain prose.

### 6.1 Pace Constraint Logic

A pace constraint is a user‑configured rule that caps how many AHLOA sites can start CX in a given geographic slice within a single ISO week. The user saves a row in the `pace_constraints` table with values for region, area, or market (any combination), a `max_sites` count, an optional `start_date`, and `project_type = 'ahloa'`. When the AHLOA Gantt is rendered for that user, the system first computes the raw CX Start for every eligible site, then groups all geo‑matching sites by the Monday of the ISO week that contains their forecasted CX. For each week, if the number of matching sites is greater than `max_sites`, the **earliest** sites are kept in the week and the rest are pushed to the following Monday with a flag `excluded_due_to_pace_constraint = true` and a label "Excluded - Pace Constraint." Cascading is recursive — if next Monday is also overflowing, the spillover keeps rolling forward until a week with capacity is reached. If the soft flag is on and a week is **under** capacity, the system pulls the earliest sites from future weeks back into the current week and stamps the note "Pulled from {original date} to fill pace constraint." A separate "strict" mode swaps the cascade for a hard drop — overflow sites are removed from the response entirely, so the user sees only what actually fits the program rate. The constraint applies only for the user who saved it and only inside `project_type = 'ahloa'`; macro pace rules never bleed into the AHLOA Gantt.

### 6.2 Vendor Capacity Logic

A vendor capacity window is a user‑configured rule that caps how many AHLOA sites a given GC (or geographic slice) can absorb inside a recurring time bucket. The user saves a row in the `gc_capacity_windows` table with a `start_date`, an `end_date` (the gap between the two defines the window length in days), an optional `vendor_name`, optional region / area / market filters, a `max_sites` count, and `project_type = 'ahloa'`. When the AHLOA Gantt runs for that user, the system computes each site's settled CX, then assigns the site to a recurring bucket index calculated as `(forecast_date − window_start).days // window_length` — so a 14‑day window starting 2026‑05‑01 produces bucket 0 = May 1–14, bucket 1 = May 15–28, and so on, repeating forward forever. Sites are first filtered to those whose vendor and geo match the window. For each bucket, if the number of matching sites exceeds `max_sites`, the **earliest** sites are kept and the rest cascade to the next bucket with a flag `excluded_due_to_crew_shortage = true` and a label "Excluded - Crew Shortage." The cascade is recursive — overflow keeps rolling forward until a bucket with capacity is reached. If a bucket is **under** capacity, the system pulls the earliest sites from future buckets back into the current bucket and stamps the note "Pulled from {original date} to fill vendor capacity window." The constraint applies only for the user who saved it and only inside `project_type = 'ahloa'`, and it runs **after** Excel CX overrides and pace constraint, so the vendor capacity sees the already‑settled forecasted CX rather than the raw formula date.

### 6.3 Skip Logic

A skip is a user (or admin) declaration that a specific AHLOA milestone does not apply to a site or geography. Skips live in `ahloa_user_skipped_prerequisites` keyed by user, milestone, and an optional geo dimension — exactly one of `market`, `area`, or both blank may be set per row, so a skip can target a single market, every market in an area, or every market for that user (the API rejects rows where both `market` and `area` are set). When the AHLOA Gantt computes a site, the engine merges the admin global `is_skipped` flag on the milestone definition with all user skip rows whose geo matches the site's geo, producing one effective skip set per site. AHLOA has no forward chain, so a skip simply removes the milestone from the count and from the on‑track percentage — it does not shift any other milestone's expected date. Skipped milestones never count toward the Delayed total, never appear in the milestone list returned to the UI, and never reduce the on‑track percentage; they are treated as "not applicable" rather than "complete." The site‑level percentage and the dashboard roll‑up therefore reflect only the milestones that genuinely apply to that site. Because the geo scope is row‑level, the same user can skip Crane for area = TX, then skip Talon Scoping just for market = Houston, and the two rules apply independently to each matching site.

### 6.4 Unskip Logic

Unskip is the inverse operation, exposed as two API endpoints: `DELETE /skip-prerequisites/{user_id}/{milestone_key}` removes one specific skip, and `DELETE /skip-prerequisites/{user_id}` clears every skip the user has saved. Internally the row is simply deleted from `ahloa_user_skipped_prerequisites` — there is no soft‑delete and no history kept. On the next Gantt render the milestone re‑enters the count for every site that was previously matching the deleted skip's geo, and its status is graded against `CX − expected_days` like any other milestone. Because skip storage is per (user, milestone, market, area) row, unskipping at one geo level does not affect a different scope — for example, a user who skipped Crane for area = TX and also for market = Houston must unskip both rows separately to fully restore the milestone everywhere. The on‑track percentage moves accordingly as the milestone count changes; if the unskipped milestone happens to already be Delayed (no actual and expected has passed, or a blank text/status field), the site's percentage will fall and the badge may shift one tier down (for example, from ON TRACK to IN PROGRESS). The Gantt response is computed fresh on every call, so the next render after the DELETE call reflects the updated skip set immediately.

---

## 7. What We'd Like Validated

1. **Eligibility filters** (Section 2) — Nokia vendor, Radio Upgrade NR, plan‑added cutoff of 2025‑03‑28, and 4225 IS NULL.
2. **12‑milestone catalog & offsets** (Section 1) — the names, owners, phases, and days‑before‑CX values.
3. **CX Start formula** (Section 3) — `max(3710, 4075) + 50` with 4225 fallback when in the past.
4. **Text / status / NAS milestones** (Section 1) — CPO and LL NTP Ready as text presence, Crane as `Yes`/`No` status, NAS Upload sourced from `stg_nas_planned_outage_activity` filtered by `nas_project_category = 'AHLOB'`.
5. **Status thresholds** (Section 4) — the 93 / 65 / 30 / 0 cuts at the milestone level and 60 / 30 / 0 cuts at the dashboard level.
6. **Blocked rule** (Section 4) — that any non‑empty delay code forces Blocked.
7. **Pace constraint behavior** (Section 6.1) — cascade vs strict mode, overflow rolls to next Monday, soft mode pulls earlier sites forward; user‑scoped, AHLOA‑only.
8. **Vendor capacity behavior** (Section 6.2) — recurring buckets per (vendor + geo), cascade to next bucket on overflow, pull‑forward on underflow; user‑scoped, AHLOA‑only.
9. **Skip semantics** (Section 6.3) — per‑user skips scoped to one market, one area, or all geos; skipped milestones excluded from the count and the percentage, not graded as Delayed.
10. **Unskip behavior** (Section 6.4) — clean deletion per (user, milestone, market, area) row; geos must be unskipped individually.
