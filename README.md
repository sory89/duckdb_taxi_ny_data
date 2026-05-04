# NYC Yellow Taxi Explorer 🚕

DuckDB-powered Streamlit dashboard — every chart is a live SQL query against a local `.duckdb` file. No server, no cloud, no manual download.

## Quick start

**Windows (PowerShell)**
```powershell
pip install duckdb streamlit pandas plotly
streamlit run app.py
```

**macOS / Linux / WSL**
```bash
./start.sh
```

First run ingests ~3 months of TLC data (~30 s). Dashboard opens at **http://localhost:8501**.

---

## How the code works

### `app.py` — dashboard (273 lines)

```
st.set_page_config()          ← must be first Streamlit call

bootstrap()                   ← @st.cache_resource : runs once per process
  └── scheduler.run_once()    ← blocking first-time ingest if no taxi.duckdb
  └── scheduler.start_in_background()   ← daemon thread, refreshes every 24h

get_con()                     ← @st.cache_resource : one DuckDB read-only connection

query(sql, months, boroughs)  ← @st.cache_data(ttl=3600) : cached per filter combo
  └── WITH filtered AS (SELECT t.*, z.Borough, z.Zone
                         FROM trips t JOIN zones z ON t.PULocationID = z.LocationID)
      {your sql here}
```

**Sidebar** — reads distinct `month_key` and `Borough` from the DB, exposes multiselects.

**Charts (all use the `query()` helper):**

| Chart | SQL |
|---|---|
| KPIs | `count(*), avg(fare), avg(tip), avg(distance), sum(fare)/sum(distance)` |
| Tip by hour | `hour(tpep_pickup_datetime), avg(tip_amount) GROUP BY hour` |
| Fare per mile | `Borough, sum(fare)/sum(distance) GROUP BY Borough` |
| Busiest zones | `Zone, Borough, count(*) GROUP BY Zone, Borough LIMIT 15` |
| Heatmap | `dayname(pickup), hour(pickup), count(*) GROUP BY day, hour` |

---

### `ingest.py` — data loader

```python
ingest(db_path, months)
  └── INSTALL httpfs; LOAD httpfs          ← enables HTTPS parquet reads
  └── CREATE TABLE IF NOT EXISTS trips … 
  └── CREATE TABLE IF NOT EXISTS zones … (from TLC CSV)
  └── for each month:
        skip if already in DB              ← idempotent
        INSERT INTO trips
          SELECT … FROM read_parquet('https://…cloudfront…YYYY-MM.parquet')
          WHERE tpep_pickup_datetime BETWEEN '{month}-01' AND '{month}-01' + 1 MONTH
            AND fare_amount > 0 AND trip_distance > 0
```

Data source: `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet`

---

### `scheduler.py` — background refresh

```python
start_in_background()
  └── daemon thread → _loop()
        └── if needs_ingest():   ← DB missing OR marker file > 24h old
              run_once()         → ingest() + touch marker file
        └── sleep 60s × 1440    ← wakes every minute, checks 24h elapsed
```

The marker file `taxi.duckdb.last_ingest` tracks when the last ingest ran.  
DuckDB allows one **write** connection (scheduler) + one **read-only** connection (dashboard) on the same file simultaneously.

---

## Project structure

```
DUCKDBTAXI/
├── app.py            # Streamlit dashboard
├── ingest.py         # DuckDB ingest from TLC CloudFront
├── scheduler.py      # Background daily refresh thread
├── demo.sql          # SQL walkthrough (duckdb CLI)
├── start.sh          # Unix/WSL launcher
├── start.bat         # Windows launcher
├── requirements.txt
└── .gitignore        # excludes .venv/ and *.duckdb
```

## Commands

```bash
./start.sh          # launch dashboard
./start.sh ingest   # force a fresh ingest now
./start.sh demo     # SQL walkthrough in duckdb CLI
```

## Requirements

- Python 3.10+
- Internet connection (first ingest only, ~236 MB cached locally after)

```
duckdb>=0.10.0
streamlit>=1.32.0
pandas>=2.0.0
plotly>=5.18.0
```
