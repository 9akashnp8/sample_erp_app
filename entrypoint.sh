#!/bin/sh
set -e

DB_PATH="/app/db/erp.db"

if [ ! -f "$DB_PATH" ]; then
    echo "No existing database found at $DB_PATH — seeding fresh data..."
    python scripts/build_employees.py
else
    echo "Existing database found at $DB_PATH — skipping seed (set RESET_DB=1 to force reseed)."
fi

if [ "$RESET_DB" = "1" ]; then
    echo "RESET_DB=1 — rebuilding database from seed data..."
    python scripts/build_employees.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
