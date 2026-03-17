1. Per-milestone status (logic.py:28-60): Each milestone gets one of three statuses based on its actual vs planned-finish date:

On Track — actual date exists and is on or before the planned date (finished on time), OR the planned date is still in the future (not yet due, but has time)
In Progress — no actual date and no planned date yet (work hasn't started / no deadline set)
Delayed — either finished late (actual > planned) or the planned date has already passed with no actual date

2. Overall site status (logic.py:63-90): The system counts how many milestones are "On Track" out of total milestones and computes a percentage (on_track_pct = on_track_count / total * 100). This percentage is matched against DB-driven threshold ranges; if no thresholds exist, hardcoded fallbacks apply:

ON TRACK — ≥60% of milestones are on track
IN PROGRESS — 30–59% on track
CRITICAL — <30% on track