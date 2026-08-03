#!/bin/sh
set -e

DB_PATH="/app/db/erp.db"


if [ ! -f "$DB_PATH" ] || [ "$RESET_DB" = "1" ]; then
    echo "Seeding database at $DB_PATH..."
    python scripts/build_employees.py
    python scripts/build_finance.py
    python scripts/build_helpdesk.py
    python scripts/build_leave.py
    python scripts/build_performance.py
else
    echo "Existing database found at $DB_PATH — skipping seed (set RESET_DB=1 to force reseed)."
fi


exec uvicorn app.main:app --host 0.0.0.0 --port 8000
