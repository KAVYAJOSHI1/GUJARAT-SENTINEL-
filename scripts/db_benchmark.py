#!/usr/bin/env python3
"""
Phase 6 -- database scalability benchmark.

Generates a realistic synthetic `vehicle_events` dataset and times the exact
queries the API issues (/vehicles/search, /vehicles/events/recent,
/analytics/overview sub-queries, retention DELETE). Reports wall-clock
latency and the EXPLAIN plan node type (index vs seq scan) at each row
count.

This is a STANDALONE script -- it never runs inside the application and it
inserts only into a disposable benchmark database. It does not create fake
analytics data anywhere the app can read.

Usage:
  DATABASE_URL=postgresql+psycopg2://sentinel:sentinel@localhost:5457/sentinel_bench \\
    .venv/bin/python scripts/db_benchmark.py --rows 10000 100000 1000000
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from datetime import datetime, timedelta

import psycopg2

random.seed(42)

DEFAULT_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://sentinel:sentinel@localhost:5457/sentinel_bench",
).replace("postgresql+psycopg2://", "postgresql://")

N_CAMERAS = 30
WINDOW_HOURS = 24
GUJ_LAT, GUJ_LON = 23.03, 72.58


def connect():
    return psycopg2.connect(DEFAULT_DSN)


def reset_events(cur):
    cur.execute("TRUNCATE vehicle_events, alerts RESTART IDENTITY CASCADE")


def ensure_cameras(cur):
    cur.execute("SELECT count(*) FROM cameras")
    if cur.fetchone()[0] >= N_CAMERAS:
        return
    cur.execute("TRUNCATE cameras RESTART IDENTITY CASCADE")
    for i in range(N_CAMERAS):
        code = f"cam{i + 1:02d}"
        lat = GUJ_LAT + random.uniform(-0.4, 0.4)
        lon = GUJ_LON + random.uniform(-0.4, 0.4)
        cur.execute(
            """INSERT INTO cameras (id, code, name, status, location_desc, location,
                                    created_at, updated_at)
               VALUES (gen_random_uuid()::text, %s, %s, 'ONLINE', %s,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326), now(), now())""",
            (code, f"Camera {code}", f"Zone {i % 6}", lon, lat),
        )


def load_events(cur, n_rows: int):
    """Bulk insert `n_rows` synthetic events with a realistic distribution:
      * 30 cameras
      * a plate pool where ~1% of plates account for most sightings
      * ~12% UNKNOWN
      * timestamps spread over the last 60 days, denser in the last 24h
      * lat/lon copied from the owning camera for ~85% of rows
    """
    reset_events(cur)

    # Server-side generation. Everything is computed INLINE per generated row
    # (a LATERAL subquery that doesn't reference `g` gets materialised once by
    # the planner, which would make every row identical) -- `r` is a per-row
    # random seed derived from `g` so the derived values genuinely vary.
    cur.execute(
        """
        WITH cam AS (
            SELECT row_number() OVER (ORDER BY code) - 1 AS n,
                   id, code, ST_Y(location) AS lat, ST_X(location) AS lon
            FROM cameras
        ),
        gen AS (
            SELECT g,
                   random() AS r_cam, random() AS r_plate, random() AS r_hot,
                   random() AS r_ts,  random() AS r_geo,   random() AS r_type,
                   random() AS r_d1,  random() AS r_d2,    random() AS r_d3,
                   random() AS r_conf, random() AS r_track
            FROM generate_series(1, %s) g
        )
        INSERT INTO vehicle_events
            (id, plate_number, plate_number_normalized, camera_id, camera_code,
             timestamp, track_id, vehicle_type, confidence_score,
             latitude, longitude, location, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            plate, plate,
            c.id, c.code,
            now() - CASE WHEN gen.r_ts < 0.08
                         THEN gen.r_d1 * interval '24 hours'
                         ELSE gen.r_d2 * interval '90 days' END,
            (gen.r_track * 5000)::int,
            (ARRAY['car','car','car','motorcycle','motorcycle','bus','truck'])[1 + floor(gen.r_type * 7)::int],
            0.55 + gen.r_conf * 0.44,
            CASE WHEN gen.r_geo < 0.85 THEN c.lat END,
            CASE WHEN gen.r_geo < 0.85 THEN c.lon END,
            CASE WHEN gen.r_geo < 0.85 THEN ST_SetSRID(ST_MakePoint(c.lon, c.lat), 4326) END,
            now(), now()
        FROM gen
        JOIN cam c ON c.n = floor(gen.r_cam * (SELECT count(*) FROM cam))::int
        CROSS JOIN LATERAL (
            SELECT CASE
                     WHEN gen.r_plate < 0.12 THEN 'UNKNOWN'
                     WHEN gen.r_plate < 0.40
                       THEN 'GJ' || lpad((floor(gen.r_hot * 20)::int)::text, 2, '0') || 'HOT' || lpad((floor(gen.r_d3 * 50)::int)::text, 2, '0')
                     ELSE 'GJ' || lpad((floor(gen.r_d1 * 40)::int)::text, 2, '0')
                          || chr(65 + floor(gen.r_d2 * 25)::int) || chr(65 + floor(gen.r_d3 * 25)::int)
                          || lpad((floor(gen.r_hot * 9999)::int)::text, 4, '0')
                   END AS plate
        ) pl
        """,
        (n_rows,),
    )
    cur.execute("ANALYZE vehicle_events")


def _plan_node(cur, sql, params):
    cur.execute("EXPLAIN (FORMAT JSON) " + sql, params)
    plan = cur.fetchone()[0][0]["Plan"]
    # walk to the first "real" scan node
    node = plan
    seen = []
    while node:
        seen.append(node.get("Node Type"))
        kids = node.get("Plans")
        node = kids[0] if kids else None
    return " > ".join(seen)


def _time(cur, sql, params, runs=5):
    # warm cache
    cur.execute(sql, params)
    cur.fetchall()
    xs = []
    for _ in range(runs):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        cur.fetchall()
        xs.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(xs), min(xs), max(xs)


def bench(cur, n_rows: int, hot_plate: str):
    now = datetime.utcnow()
    win = now - timedelta(hours=WINDOW_HOURS)
    results = []

    def run(label, sql, params):
        med, lo, hi = _time(cur, sql, params)
        plan = _plan_node(cur, sql, params)
        results.append((label, med, lo, hi, plan))

    # 1. /vehicles/search  (WHERE plate = ? ORDER BY timestamp ASC LIMIT 200)
    run(
        "vehicles/search (hot plate)",
        """SELECT ve.*, c.name, c.code FROM vehicle_events ve
           LEFT JOIN cameras c ON c.id = ve.camera_id
           WHERE ve.plate_number_normalized = %s
           ORDER BY ve.timestamp ASC LIMIT 200""",
        (hot_plate,),
    )

    # 2. /vehicles/events/recent  (ORDER BY timestamp DESC LIMIT 50)
    run(
        "vehicles/events/recent",
        """SELECT ve.*, c.name FROM vehicle_events ve
           LEFT JOIN cameras c ON c.id = ve.camera_id
           ORDER BY ve.timestamp DESC LIMIT 50""",
        (),
    )

    # 3. analytics: total count (all-time)
    run("analytics: COUNT(*) all-time", "SELECT count(*) FROM vehicle_events", ())

    # 4. analytics: windowed count
    run(
        "analytics: COUNT(*) in window",
        "SELECT count(*) FROM vehicle_events WHERE timestamp >= %s",
        (win,),
    )

    # 5. analytics: distinct plates in window
    run(
        "analytics: COUNT(DISTINCT plate) in window",
        """SELECT count(DISTINCT plate_number_normalized) FROM vehicle_events
           WHERE timestamp >= %s AND plate_number_normalized <> 'UNKNOWN'""",
        (win,),
    )

    # 5b. analytics: consolidated windowed scalars (Phase 6 -- one scan for
    #     total + readable + distinct, replacing 3 separate queries)
    run(
        "analytics: consolidated window scalars (NEW)",
        """SELECT count(*),
                  count(*) FILTER (WHERE plate_number_normalized <> 'UNKNOWN'),
                  count(DISTINCT plate_number_normalized)
                       FILTER (WHERE plate_number_normalized <> 'UNKNOWN')
           FROM vehicle_events WHERE timestamp >= %s""",
        (win,),
    )

    # 6. analytics: detections by type (all-time GROUP BY)
    run(
        "analytics: GROUP BY vehicle_type (all-time)",
        """SELECT vehicle_type, count(*) FROM vehicle_events
           GROUP BY vehicle_type ORDER BY count(*) DESC""",
        (),
    )

    # 7. analytics: detections by camera in window -- OLD (join + group by name)
    run(
        "analytics: by camera in window (OLD join+group)",
        """SELECT ve.camera_code, c.name, count(*) FROM vehicle_events ve
           LEFT JOIN cameras c ON c.id = ve.camera_id
           WHERE ve.timestamp >= %s
           GROUP BY ve.camera_code, c.name ORDER BY count(*) DESC LIMIT 8""",
        (win,),
    )
    # 7b. analytics: detections by camera -- NEW (aggregate first, then name lookup)
    run(
        "analytics: by camera in window (NEW agg-then-join)",
        """SELECT camera_code, count(*) FROM vehicle_events
           WHERE timestamp >= %s
           GROUP BY camera_code ORDER BY count(*) DESC LIMIT 8""",
        (win,),
    )

    # 8. analytics: top plates in window
    run(
        "analytics: top plates in window",
        """SELECT plate_number_normalized, count(*) FROM vehicle_events
           WHERE timestamp >= %s AND plate_number_normalized <> 'UNKNOWN'
           GROUP BY plate_number_normalized ORDER BY count(*) DESC LIMIT 8""",
        (win,),
    )

    # 9. analytics: hourly buckets in window
    run(
        "analytics: hourly buckets in window",
        """SELECT date_trunc('hour', timestamp), count(*) FROM vehicle_events
           WHERE timestamp >= %s GROUP BY 1 ORDER BY 1""",
        (win,),
    )

    # 10. retention candidate scan (30-day cutoff, alert-safe anti-join) -- SELECT
    #     form so we measure the planner cost without deleting.
    cutoff = now - timedelta(days=30)
    run(
        "retention: count purgeable rows",
        """SELECT count(*) FROM vehicle_events ve
           WHERE ve.timestamp < %s
             AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.vehicle_event_id = ve.id)""",
        (cutoff,),
    )

    print(f"\n===== {n_rows:,} vehicle_events =====")
    print(f"{'query':<44}{'p50 ms':>10}{'min':>9}{'max':>9}   plan")
    print("-" * 110)
    for label, med, lo, hi, plan in results:
        print(f"{label:<44}{med:>10.2f}{lo:>9.2f}{hi:>9.2f}   {plan}")
    return results


def pick_hot_plate(cur):
    cur.execute(
        """SELECT plate_number_normalized FROM vehicle_events
           WHERE plate_number_normalized <> 'UNKNOWN'
           GROUP BY plate_number_normalized ORDER BY count(*) DESC LIMIT 1"""
    )
    row = cur.fetchone()
    if row is None:
        raise SystemExit("data generation produced no non-UNKNOWN plates -- check load_events()")
    return row[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, nargs="+", default=[10_000, 100_000, 1_000_000])
    ap.add_argument("--keep", action="store_true", help="don't truncate at the end")
    ap.add_argument("--skip-load", action="store_true",
                    help="benchmark whatever is already in vehicle_events (re-run after an index change)")
    args = ap.parse_args()

    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid
    except psycopg2.Error:
        pass
    ensure_cameras(cur)

    if args.skip_load:
        cur.execute("SELECT count(*) FROM vehicle_events")
        n = cur.fetchone()[0]
        cur.execute("ANALYZE vehicle_events")
        bench(cur, n, pick_hot_plate(cur))
    else:
        for n in args.rows:
            print(f"\nloading {n:,} rows ...", flush=True)
            t0 = time.time()
            load_events(cur, n)
            print(f"  loaded in {time.time() - t0:.1f}s", flush=True)
            hot = pick_hot_plate(cur)
            bench(cur, n, hot)
        if not args.keep:
            reset_events(cur)
    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
