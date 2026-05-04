"""
NYC Yellow Taxi Explorer — DuckDB-powered Streamlit dashboard.
Every chart is a live SQL query against a local DuckDB file.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

import scheduler

# ── Page config (must be first Streamlit call) ───────────────────────────────

st.set_page_config(
    page_title="NYC Yellow Taxi Explorer",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB = scheduler.DB_PATH

# ── Bootstrap: first-time ingest + background daily refresh ──────────────────

@st.cache_resource(show_spinner=False)
def bootstrap() -> bool:
    if not Path(DB).exists():
        with st.spinner("First-time ingest from the NYC TLC public parquet — this takes ~30 s…"):
            scheduler.run_once()
    scheduler.start_in_background()
    return True


bootstrap()

# ── DuckDB connection + cached query helper ───────────────────────────────────

@st.cache_resource
def get_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB, read_only=True)


@st.cache_data(show_spinner=False, ttl=3600)
def query(sql_tail: str, months: tuple[str, ...], boroughs: tuple[str, ...]) -> pd.DataFrame:
    """Run *sql_tail* against a filtered CTE that joins trips + zones."""
    sql = f"""
    WITH filtered AS (
        SELECT t.*, z.Borough, z.Zone
        FROM trips t
        JOIN zones z ON t.PULocationID = z.LocationID
    )
    {sql_tail}
    """
    return get_con().execute(sql).df()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    # ── Months available in the DB ──
    try:
        all_months: list[str] = (
            get_con()
            .execute("SELECT DISTINCT month_key FROM trips ORDER BY month_key")
            .df()["month_key"]
            .tolist()
        )
    except Exception:
        all_months = []

    months: list[str] = st.multiselect(
        "Months",
        options=all_months,
        default=all_months,
    )

    # ── Boroughs available in the DB ──
    try:
        all_boroughs: list[str] = (
            get_con()
            .execute("SELECT DISTINCT Borough FROM zones WHERE Borough <> 'Unknown' ORDER BY Borough")
            .df()["Borough"]
            .tolist()
        )
    except Exception:
        all_boroughs = []

    boroughs: list[str] = st.multiselect(
        "Boroughs",
        options=all_boroughs,
        default=all_boroughs,
    )

    st.divider()

    # ── DB metadata ──
    if Path(DB).exists():
        size_mb = Path(DB).stat().st_size / 1_048_576
        st.caption(f"DB: `{DB}` · {size_mb:.1f} MB")

    if scheduler.MARKER.exists():
        last = pd.Timestamp(
            scheduler.MARKER.stat().st_mtime, unit="s", tz="UTC"
        ).tz_convert("America/New_York")
        st.caption(f"Last ingest: {last:%Y-%m-%d %H:%M %Z}")
        st.caption("Auto-refreshes once per day in the background.")

# ── Guard: need at least one month and borough ────────────────────────────────

st.title("NYC Yellow Taxi Explorer")
st.caption("DuckDB-powered — every chart is a live SQL query")

if not months or not boroughs:
    st.warning("Pick at least one month and one borough in the sidebar.")
    st.stop()

m = tuple(months)
b = tuple(boroughs)

# ── KPI row ───────────────────────────────────────────────────────────────────

kpis = query(
    f"""
    SELECT
        count(*)                             AS trips,
        avg(fare_amount)                     AS avg_fare,
        avg(tip_amount)                      AS avg_tip,
        avg(trip_distance)                   AS avg_miles,
        sum(fare_amount) / sum(trip_distance) AS fare_per_mile
    FROM filtered
    WHERE month_key IN {m}
      AND Borough    IN {b}
    """,
    m, b,
).iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Trips",         f"{int(kpis.trips):,}")
c2.metric("Avg fare",      f"${kpis.avg_fare:,.2f}")
c3.metric("Avg tip",       f"${kpis.avg_tip:,.2f}")
c4.metric("Avg distance",  f"{kpis.avg_miles:,.2f} mi")
c5.metric("Fare per mile", f"${kpis.fare_per_mile:,.2f}")

st.divider()

# ── Row 1 — tip by hour  +  fare per mile by borough ─────────────────────────

left, right = st.columns(2)

with left:
    st.subheader("Average tip by hour of day")
    df = query(
        f"""
        SELECT hour(tpep_pickup_datetime) AS hour_of_day,
               avg(tip_amount)            AS avg_tip
        FROM filtered
        WHERE month_key IN {m} AND Borough IN {b}
        GROUP BY hour_of_day
        ORDER BY hour_of_day
        """,
        m, b,
    )
    fig = px.line(
        df, x="hour_of_day", y="avg_tip", markers=True,
        labels={"hour_of_day": "Hour", "avg_tip": "Avg tip ($)"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=360)
    st.plotly_chart(fig, use_container_width=True)


with right:
    st.subheader("Fare per mile by borough")
    df = query(
        f"""
        SELECT Borough,
               sum(fare_amount) / sum(trip_distance) AS fare_per_mile
        FROM filtered
        WHERE month_key IN {m} AND Borough IN {b}
          AND trip_distance > 0
        GROUP BY Borough
        ORDER BY fare_per_mile DESC
        """,
        m, b,
    )
    fig = px.bar(
        df, x="Borough", y="fare_per_mile",
        labels={"fare_per_mile": "$ / mile"},
        text=df["fare_per_mile"].round(2),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=360)
    st.plotly_chart(fig, use_container_width=True)

# ── Row 2 — busiest pickup zones ─────────────────────────────────────────────

st.subheader("Busiest pickup zones (top 15)")
df = query(
    f"""
    SELECT Zone, Borough, count(*) AS pickups
    FROM filtered
    WHERE month_key IN {m} AND Borough IN {b}
    GROUP BY Zone, Borough
    ORDER BY pickups DESC
    LIMIT 15
    """,
    m, b,
)
fig = px.bar(
    df, x="pickups", y="Zone", color="Borough",
    orientation="h",
    labels={"pickups": "Pickups"},
    category_orders={"Zone": df["Zone"].tolist()},
)
fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=420, yaxis={"autorange": "reversed"})
st.plotly_chart(fig, use_container_width=True)

# ── Row 3 — day-of-week × hour heatmap ───────────────────────────────────────

st.subheader("Pickups by day of week & hour")
df = query(
    f"""
    SELECT dayname(tpep_pickup_datetime) AS day,
           hour(tpep_pickup_datetime)   AS hour,
           count(*)                      AS trips
    FROM filtered
    WHERE month_key IN {m} AND Borough IN {b}
    GROUP BY day, hour
    """,
    m, b,
)

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
df["day"] = pd.Categorical(df["day"], categories=day_order, ordered=True)

pivot = (
    df.pivot(index="day", columns="hour", values="trips")
      .reindex(day_order)
      .fillna(0)
)

fig = px.imshow(
    pivot,
    aspect="auto",
    color_continuous_scale="Viridis",
    labels=dict(x="Hour of day", y="", color="Pickups"),
)
fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320)
st.plotly_chart(fig, use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────

with st.expander("What's running under the hood?"):
    st.code(
        """
-- Every chart on this page is one of these:
SELECT hour(tpep_pickup_datetime), avg(tip_amount)              FROM trips JOIN zones ... GROUP BY 1;
SELECT Borough, sum(fare_amount)/sum(trip_distance)             FROM trips JOIN zones ... GROUP BY 1;
SELECT Zone, Borough, count(*) AS pickups                       FROM trips JOIN zones ... GROUP BY 1,2;
SELECT dayname(tpep_pickup_datetime), hour(...), count(*)       FROM trips JOIN zones ... GROUP BY 1,2;
""",
        language="sql",
    )

st.caption(
    "DuckDB executes these against the local 'taxi.duckdb' file in-process — "
    "no server, no network calls once ingest is done."
)
