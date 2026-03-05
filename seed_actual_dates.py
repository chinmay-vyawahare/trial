"""
Seed synthetic actual dates into the staging table.

Updates existing rows in nokia_bkg_sample.stg_ndpd_mbt_tmobile_macro_combined
to populate milestone actual date columns with realistic values based on
each site's planned start date + expected duration + small random offset.

This gives the SLA History feature data to compute from.

Usage:
    cd backend
    python seed_actual_dates.py

Only updates rows matching the base WHERE clause (NTM sites with a GC assigned).
Populates ~70% of rows with actual dates to simulate a mix of completed
and in-progress milestones.
"""

import random
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from app.core.config import settings

password_encoded = quote_plus(settings.PG_PASSWORD)
engine = create_engine(
    f"postgresql+psycopg2://{settings.PG_USER}:{password_encoded}"
    f"@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DATABASE}",
    pool_pre_ping=True,
)

# Milestone chain: key → (actual_date_column, depends_on_key, default_expected_days, gap_days)
# Order matters — process predecessors first
MILESTONE_CHAIN = [
    # key, actual_col, depends_on_key, expected_days, gap_days
    ("3710",      "pj_a_3710_ran_entitlement_complete_finish",               None,    0,  1),
    ("1310",      "ms_1310_pre_construction_package_received_actual",         "3710",  2,  0),
    ("site_walk", "ms_1316_pre_con_site_walk_completed_actual",              "1310",  7,  1),
    ("1323",      "ms_1323_ready_for_scoping_actual",                         "site_walk", 3, 1),
    ("1327",      "ms_1327_scoping_and_quoting_package_validated_actual",     "1323",  7,  1),
    # After 1327, the graph branches — process all branches
    ("3850",      "pj_a_3850_bom_submitted_bom_in_bat_finish",               "1327",  7,  1),
    ("3875",      "pj_a_3875_bom_received_bom_in_aims_finish",               "3850",  21, 1),
    ("quote",     "ms_1331_scoping_package_submitted_actual",                 "1327",  7,  1),
    ("1555",      "ms1555_construction_complete_spo_issued_date",             "quote", 19, 1),
    ("steel",     "pj_steel_received_date",                                   "1327",  14, 1),
    ("3925",      "pj_a_3925_msl_pickup_date_finish",                        "steel", 5,  1),
    ("1407",      "ms_1407_tower_ntp_validated_actual",                        "1327",  7,  1),
]

# Text columns that just need a non-empty value when "complete"
TEXT_COLUMNS = {
    "cpo": "ms1555_construction_complete_so_header",
    "4000": "pj_a_4000_ll_ntp_received",
}

# Steel status column
STEEL_STATUS_COL = "pj_steel_received_status"

PLANNED_START_COL = "pj_p_3710_ran_entitlement_complete_finish"

BASE_WHERE = (
    "smp_name = 'NTM' "
    "AND COALESCE(TRIM(construction_gc), '') != '' "
    "AND pj_a_4225_construction_start_finish IS NULL"
)


def run():
    with engine.connect() as conn:
        # Get all site rows
        rows = conn.execute(text(f"""
            SELECT s_site_id, {PLANNED_START_COL}
            FROM public.stg_ndpd_mbt_tmobile_macro_combined
            WHERE {BASE_WHERE}
              AND {PLANNED_START_COL} IS NOT NULL
        """)).fetchall()

        print(f"Found {len(rows)} sites with a planned start date.")
        if not rows:
            print("No rows to update.")
            return

        updated = 0
        for site_id, planned_start_raw in rows:
            if planned_start_raw is None:
                continue

            # Parse planned_start to a date object
            if isinstance(planned_start_raw, str):
                try:
                    planned_start = datetime.strptime(planned_start_raw[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
            elif isinstance(planned_start_raw, (date, datetime)):
                planned_start = planned_start_raw if isinstance(planned_start_raw, date) else planned_start_raw.date()
            else:
                continue

            # 70% of sites get actual dates (simulate completed milestones)
            if random.random() > 0.70:
                continue

            # Per-milestone skip probability (20% chance each milestone is not yet done)
            skip_prob = 0.20

            # Track computed actual dates per milestone key
            actual_dates = {}
            set_clauses = []
            params = {"site_id": site_id}

            for key, col, dep_key, expected, gap in MILESTONE_CHAIN:
                # Each milestone has a chance of not being completed yet
                # But milestones in the first 5 (up to 1327) are always completed
                first_five = {"3710", "1310", "site_walk", "1323", "1327"}
                if key not in first_five and random.random() < skip_prob:
                    continue  # this milestone not done yet

                # Compute the actual date
                if dep_key is None:
                    # Root milestone — actual = planned_start + small random offset
                    offset = random.randint(-2, 3)
                    actual = planned_start + timedelta(days=offset)
                else:
                    pred_actual = actual_dates.get(dep_key)
                    if pred_actual is None:
                        continue  # predecessor not done, skip this one
                    # actual = predecessor_actual + gap + expected + random offset (-3 to +5)
                    offset = random.randint(-3, 5)
                    actual = pred_actual + timedelta(days=gap + expected + offset)

                actual_dates[key] = actual
                param_name = f"d_{key}"
                set_clauses.append(f"{col} = :{param_name}")
                params[param_name] = actual

            # Set steel status to 'A' if steel date was set
            if "steel" in actual_dates:
                set_clauses.append(f"{STEEL_STATUS_COL} = :steel_status")
                params["steel_status"] = "A"

            # Set text columns for completed milestones
            # cpo depends on quote → 1555 chain; set if 1555 was reached
            if "1555" in actual_dates:
                set_clauses.append(f"{TEXT_COLUMNS['cpo']} = :cpo_val")
                params["cpo_val"] = f"SO-{random.randint(10000, 99999)}"

            # 4000 (Access Confirmation) — set if 1407 was reached
            if "1407" in actual_dates:
                set_clauses.append(f"{TEXT_COLUMNS['4000']} = :access_val")
                params["access_val"] = f"NTP-{random.randint(1000, 9999)}"

            # Also seed the drone column for site_walk (min of two)
            if "site_walk" in actual_dates:
                drone_offset = random.randint(0, 3)
                drone_date = actual_dates["site_walk"] + timedelta(days=drone_offset)
                set_clauses.append("ms_1321_talon_view_drone_svcs_actual = :drone_date")
                params["drone_date"] = drone_date

            if not set_clauses:
                continue

            set_sql = ", ".join(set_clauses)
            conn.execute(text(f"""
                UPDATE public.stg_ndpd_mbt_tmobile_macro_combined
                SET {set_sql}
                WHERE s_site_id = :site_id
            """), params)
            updated += 1

        conn.commit()
        print(f"Updated {updated} sites with synthetic actual dates.")


if __name__ == "__main__":
    run()
