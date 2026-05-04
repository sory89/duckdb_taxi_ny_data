"""
Ingest NYC TLC yellow-taxi parquet straight off CloudFront into a local
DuckDB file. Idempotent: re-running with new --months only fetches the
ones that aren't already in the table.

python ingest.py                          # default: 3 most-recent available months
python ingest.py --months 2024-01 2024-02
python ingest.py --db taxi.duckdb --months 2024-06
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import duckdb

# ── Constants ──────────────────────────────────────────────────────────────────
NUM_MONTHS = 3
LAG_MONTHS = 4

TLC_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "yellow_tripdata_{month}.parquet"
)
ZONE_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"


def make_default_months(n: int = NUM_MONTHS, lag: int = LAG_MONTHS) -> list[str]:
    """Return the most-recent YYYY-MM strings expected to be available on TLC."""
    today = date.today()
    y, m = today.year, today.month - lag
    while m <= 0:
        m += 12
        y -= 1
    out: list[str] = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m <= 0:
            m += 12
            y -= 1
    return out


DEFAULT_MONTHS = make_default_months()


def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()[0] > 0


def ingest(db_path: str, months: list[str]) -> None:
    con = duckdb.connect(db_path)
    con.execute("INSTALL httpfs; LOAD httpfs;")

    # Create trips table
    con.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            tpep_pickup_datetime  TIMESTAMP,
            tpep_dropoff_datetime TIMESTAMP,
            passenger_count       DOUBLE,
            trip_distance         DOUBLE,
            fare_amount           DOUBLE,
            tip_amount            DOUBLE,
            total_amount          DOUBLE,
            PULocationID          INTEGER,
            DOLocationID          INTEGER,
            month_key             VARCHAR
        )
    """)

    # Create zones table (once)
    if not _table_exists(con, "zones"):
        con.execute(f"CREATE TABLE zones AS SELECT * FROM read_csv_auto('{ZONE_URL}')")

    for month in months:
        existing = con.execute(
            "SELECT count(*) FROM trips WHERE month_key = ?", [month]
        ).fetchone()[0]

        if existing > 0:
            print(f"[skip] {month} already in DB ({existing:,} rows)")
            continue

        url = TLC_URL.format(month=month)
        print(f"[ingest] {month} <- {url}")
        t0 = time.perf_counter()

        try:
            con.execute(f"""
                INSERT INTO trips
                SELECT
                    tpep_pickup_datetime,
                    tpep_dropoff_datetime,
                    passenger_count,
                    trip_distance,
                    fare_amount,
                    tip_amount,
                    total_amount,
                    PULocationID,
                    DOLocationID,
                    '{month}' AS month_key
                FROM read_parquet('{url}')
                WHERE tpep_pickup_datetime >= TIMESTAMP '{month}-01'
                  AND tpep_pickup_datetime <  TIMESTAMP '{month}-01' + INTERVAL 1 MONTH
                  AND fare_amount   > 0
                  AND trip_distance > 0
                  AND tip_amount BETWEEN 0 AND 500
            """)
        except duckdb.HTTPException as e:
            print(f"[skip] {month} not available ({e})")
            continue

        n = con.execute(
            "SELECT count(*) FROM trips WHERE month_key = ?", [month]
        ).fetchone()[0]
        print(f"         {n:>10,} rows in {time.perf_counter()-t0:5.1f}s")

    total = con.execute("SELECT count(*) FROM trips").fetchone()[0]
    size_mb = Path(db_path).stat().st_size / 1_048_576
    print(f"[done]   {total:,} total trips · {db_path} ~{size_mb:.1f} MB")
    con.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="taxi.duckdb")
    p.add_argument("--months", nargs="+", default=DEFAULT_MONTHS, metavar="YYYY-MM")
    args = p.parse_args()
    ingest(args.db, args.months)


if __name__ == "__main__":
    main()
