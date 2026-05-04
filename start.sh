#!/usr/bin/env bash
# Single entry point.
#
# ./start.sh        launch the dashboard (auto-installs deps, auto-ingests data,
#                   and refreshes once per day in the background)
# ./start.sh demo   SQL-only walkthrough (duckdb CLI on remote parquet)
# ./start.sh bench  parquet-vs-csv race
# ./start.sh ingest force an ingest cycle right now (rarely needed)

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    echo "[setup] creating $VENV (one-time, ~20s)"
    python3 -m venv "$VENV"
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r requirements.txt
  fi
}

case "${1:-app}" in
  app)
    ensure_venv
    exec "$VENV/bin/streamlit" run app.py
    ;;

  ingest)
    ensure_venv
    shift || true
    "$PY" ingest.py "$@"
    ;;

  demo)
    exec duckdb -init demo.sql
    ;;

  bench)
    exec duckdb < benchmark.sql
    ;;

  *)
    echo "usage: $0 [app|demo|bench|ingest]" >&2
    exit 1
    ;;
esac