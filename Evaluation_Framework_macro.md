
## 1. The 14 Macro Milestones (loaded from the database)

Every macro site is graded against the same fixed catalog of 14 milestones, stored in `milestone_definitions` and `milestone_columns`. Order, owners, durations, and dependencies are admin‑configurable.

| # | Milestone | Owner | Phase | Duration (days) | Depends on |
|---|---|---|---|---|---|
| 1 | Entitlement Complete (MS 3710) | TMO | Pre‑Con | 0 | — (root) |
| 2 | Pre‑NTP Document Received (MS 1310) | Proj Ops | Pre‑Con | 2 | 3710 |
| 3 | Site Walk Performed | CM | Pre‑Con | 7 | 1310 |
| 4 | Ready for Scoping (MS 1323) | SE‑CoE | Pre‑Con | 3 | Site Walk |
| 5 | Scoping Validated by GC (MS 1327) | SE‑CoE | Scoping | 7 | 1323 |
| 6 | BOM in BAT (MS 3850) | TMO | Scoping | max of parents | 3710 + 1327 |
| 7 | Quote Submitted to Customer | PM | Scoping | 7 | 1327 |
| 8 | BOM Received in AIMS (MS 3875) | TMO | Material & NTP | 21 | 3850 |
| 9 | CPO Available | TMO | Material & NTP | 14 (text) | Quote |
| 10 | SPO Issued (MS 1555) | PDM | Material & NTP | 2 | CPO |
| 11 | Steel Received (if applicable) | GC | Material & NTP | 14 (date + status) | 1327 |
| 12 | Material Pickup by GC (MS 3925) | GC | Material & NTP | 5 | 3875 |
| 13 | NTP Received (MS 1407) | TMO | Material & NTP | 7 | 1327 |
| 14 | Access Confirmation (MS 4000) | CM | Material & NTP | 7 (text) | 1327 |

Five milestones (3925, Steel, 1555, 4000, 1407) are **tails** — their finish dates plus a per‑tail buffer (4 / 7 / 5 / 7 / 7) feed the Forecasted CX Start. A further global **4‑day** buffer (`gantt_config.CX_START_OFFSET_DAYS`) is added on top. CPO and Access Confirmation are text‑presence checks; Steel is a date + status check (status `A` uses the date, `N` / blank auto‑skips).

---

## 2. Status Vocabulary

**Per‑milestone:** On Track (actual ≤ planned, or planned still in future), In Progress (no actual, planned in future), Delayed (actual > planned, or planned passed with no actual).

**Per‑site:** percentage of On Track milestones is matched against `constraint_thresholds` — READY ≥ 93 %, ON TRACK 65 – 92.99 %, IN PROGRESS 30 – 64.99 %, CRITICAL < 30 %.

**Blocked:** any populated `pj_construction_complete_delay_code` forces Blocked, overriding the percentage.

**Dashboard:** portfolio‑level percentage of On Track sites — ON TRACK ≥ 60 %, IN PROGRESS 30 – 59.99 %, CRITICAL < 30 %. Blocked and excluded sites are reported separately, not in the percentage base.

---

## 3. Forecast Gantt Logic

The Macro forecast walks the dependency graph **forward** from the planned start anchor (`pj_p_3710_ran_entitlement_complete_finish`). For each milestone, planned start = the latest of its predecessors' finishes plus its `start_gap_days` (typically 1), and planned finish = planned start + `expected_days`. Reality wins: if a predecessor has a real actual finish, downstream milestones anchor on `actual_finish + 1` instead of the calculated date — so once a milestone has actually happened, the chart self‑corrects. Multi‑parent milestones (BOM in BAT depends on both 3710 and 1327) take the **max** of parents' durations as duration and the **latest** parent finish as anchor. Forecasted CX Start = max over the 5 tails of (tail planned finish + tail buffer) + the 4‑day CX offset. If that date is already in the past, the system bumps it to **today + 7** with a label: "Ready for schedule" if every milestone has an actual, otherwise "Delayed due to {first missing milestone} by N days." The Actual view is the same engine in reverse — it anchors on the locked CX (`pj_p_4225_construction_start_finish`), subtracts each milestone's persisted `back_days`, and grades actuals against those backward dates.

---

## 4. Pace Constraint, Vendor Capacity, Skip & Unskip — Gantt Logic Detail

### 4.1 Pace Constraint Logic

A pace constraint is a user‑configured rule that caps how many macro sites can start CX in a given geographic slice within a single ISO week. The user saves a row in the `pace_constraints` table with values for region, area, or market (any combination), a `max_sites` count, an optional `start_date`, and `project_type = 'macro'`. When the Macro Gantt is rendered for that user, the system first computes the raw forecasted CX for every eligible site, then groups all geo‑matching sites by the Monday of the ISO week that contains their forecasted CX. For each week, if the number of matching sites is greater than `max_sites`, the **earliest** sites are kept and the rest are pushed to the following Monday with a flag `excluded_due_to_pace_constraint = true` and a label "Excluded - Pace Constraint." Cascading is recursive — if next Monday is also overflowing, the spillover keeps rolling forward until a week with capacity is reached. If the soft flag is on and a week is **under** capacity, the system pulls the earliest sites from future weeks back into the current week and stamps the note "Pulled from {original date} to fill pace constraint." A separate "strict" mode swaps the cascade for a hard drop — overflow sites are removed from the response entirely. The constraint applies only for the user who saved it and only inside `project_type = 'macro'`; AHLOA pace rules never bleed into the Macro Gantt.

### 4.2 Vendor Capacity Logic

A vendor capacity window is a user‑configured rule that caps how many macro sites a given GC (or geographic slice) can absorb inside a recurring time bucket. The user saves a row in the `gc_capacity_windows` table with a `start_date`, an `end_date` (the gap between the two defines the window length in days), an optional `vendor_name`, optional region / area / market filters, a `max_sites` count, and `project_type = 'macro'`. When the Macro Gantt runs, the system computes each site's settled CX (after Excel overrides and pace), then assigns the site to a recurring bucket index calculated as `(forecast_date − window_start).days // window_length` — so a 14‑day window starting 2026‑05‑01 produces bucket 0 = May 1–14, bucket 1 = May 15–28, and so on, repeating forward forever. Sites are first filtered to those whose vendor and geo match the window. For each bucket, if the number of matching sites exceeds `max_sites`, the **earliest** sites are kept and the rest cascade to the next bucket with a flag `excluded_due_to_crew_shortage = true` and a label "Excluded - Crew Shortage." The cascade is recursive — overflow keeps rolling forward until a bucket with capacity is reached. If a bucket is **under** capacity, the system pulls the earliest sites from future buckets back into the current bucket and stamps the note "Pulled from {original date} to fill vendor capacity window." The constraint applies only for the user who saved it and only inside `project_type = 'macro'`, and it runs **after** Excel CX overrides and pace constraint, so the vendor capacity sees the already‑settled forecasted CX rather than the raw formula date.

### 4.3 Skip Logic

A skip is a user (or admin) declaration that a specific macro milestone does not apply. Skips live in `user_skipped_prerequisites` keyed by user and milestone, plus an admin‑level `is_skipped` flag on the milestone definition itself; the two are merged into a single set of skipped milestone keys before the chain runs. When the Macro Gantt computes a site, the engine treats a skipped milestone's duration as **zero** so its planned start equals its planned finish and downstream milestones anchor earlier through the chain — the skipped node is then dropped from the response, and the dependency map walks through it (so A → B(skipped) → C shows C's preceding as A). Skipped milestones never count toward the Delayed total, never appear in the milestone list returned to the UI, and never reduce the on‑track percentage; they are treated as "not applicable" rather than "complete." Because skipping shrinks the chain, the Forecasted CX Start can move earlier — this is the intended effect, not a side‑effect. The site‑level percentage and the dashboard roll‑up therefore reflect only the milestones that genuinely apply to that site.

### 4.4 Unskip Logic

Unskip is the inverse operation, exposed as `DELETE /skip-prerequisites/{user_id}/{milestone_key}` to remove one specific skip and `DELETE /skip-prerequisites/{user_id}` to clear every skip the user has saved. Internally the row is simply deleted from `user_skipped_prerequisites` — no soft‑delete and no history kept. On the next Gantt render the dependency walk picks the milestone back up with its full `expected_days` duration, the chain re‑extends, downstream planned dates push back out, and the milestone reappears in the response with a real status. The on‑track percentage moves accordingly as the milestone count changes; if the unskipped milestone happens to already be Delayed, the site's percentage will fall and the badge may shift one tier down. Because the Forecasted CX Start depends on the chain length, unskipping a previously skipped milestone may also push the CX date forward — again, intended behavior.

---

## 5. What We'd Like Validated

1. **Milestone catalog & dependencies** (Section 1) — the 14 names, owners, durations, and the dependency edges (especially the multi‑parent BOM in BAT case).
2. **Tail buffers & CX offset** (Section 1) — 4 / 7 / 5 / 7 / 7 plus the global 4‑day buffer.
3. **Status thresholds** (Section 2) — 93 / 65 / 30 / 0 at the milestone level and 60 / 30 / 0 at the dashboard level.
4. **Blocked rule** (Section 2) — any non‑empty delay code forces Blocked.
5. **Forecast logic** (Section 3) — forward dependency walk, "reality wins" actual + 1 anchoring, multi‑parent max behavior, and the past‑date reschedule rule (today + 7 with "Ready for schedule" / "Delayed due to X" note).
6. **Pace constraint behavior** (Section 4.1) — cascade vs strict mode, overflow rolls to next Monday, soft mode pulls earlier sites forward; user‑scoped, Macro‑only.
7. **Vendor capacity behavior** (Section 4.2) — recurring buckets per (vendor + geo), cascade to next bucket on overflow, pull‑forward on underflow; user‑scoped, Macro‑only.
8. **Skip semantics** (Section 4.3) — skipped milestone duration treated as zero, dropped from the response, chain shrinks; not graded as Delayed.
9. **Unskip behavior** (Section 4.4) — clean deletion; chain re‑extends and CX may push forward on the next render.
