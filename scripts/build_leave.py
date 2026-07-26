"""
Builds/seeds the leave module table: leave_requests.
Assumes employees table already exists (run build_employees.py first).
Re-run any time to reset the leave_requests table to seed state.
"""
import sqlite3
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_leave.sql")


def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS leave_requests")
    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())

    # Sanity check: employees table must already exist and be populated
    try:
        emp_count = cur.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    except sqlite3.OperationalError:
        raise RuntimeError(
            "employees table not found. Run scripts/build_employees.py first."
        )
    if emp_count == 0:
        raise RuntimeError("employees table is empty. Run scripts/build_employees.py first.")

    # (employee_id, leave_type, status, start_date, end_date, reason)
    # Several Unpaid+Approved rows fall in July 2026 (later than the already
    # seeded Apr-Jun 2026 payslip history) — including one for E-2043, the
    # running example used throughout the README — so generating a July 2026
    # payslip via the live API demonstrates the new leave_deduction math.
    # Unpaid entries are kept to single days to sidestep the calendar-days
    # (vs. working-days) simplification documented in schema_leave.sql.
    leave_requests = [
        ("E-2043", "Unpaid", "Approved", "2026-07-06", "2026-07-06", "Personal matter"),
        ("E-1187", "Annual", "Approved", "2026-06-08", "2026-06-12", "Family vacation"),
        ("E-3320", "Sick", "Approved", "2026-05-14", "2026-05-15", "Flu"),
        ("E-1902", "Unpaid", "Approved", "2026-07-13", "2026-07-13", "Extended personal leave"),
        ("E-4501", "Annual", "Approved", "2026-07-20", "2026-07-24", "Summer trip"),
        ("E-2765", "Unpaid", "Rejected", "2026-07-15", "2026-07-16", "Requested too close to a product launch"),
        ("E-2891", "Sick", "Approved", "2026-06-25", "2026-06-25", "Doctor's appointment"),
        ("E-3110", "Other", "Approved", "2026-07-10", "2026-07-10", "Jury duty"),
        ("E-3502", "Annual", "Cancelled", "2026-08-03", "2026-08-07", "Trip cancelled"),
        ("E-2210", "Unpaid", "Approved", "2026-07-27", "2026-07-27", "Personal matter"),
        ("E-4890", "Sick", "Approved", "2026-07-02", "2026-07-03", "Migraine"),
        ("E-1755", "Unpaid", "Approved", "2026-06-30", "2026-06-30", "Personal matter"),
        ("E-1000", "Annual", "Approved", "2026-08-10", "2026-08-14", "Family time"),
        ("E-1001", "Other", "Approved", "2026-07-08", "2026-07-08", "Volunteering"),
    ]

    for employee_id, leave_type, status, start_date, end_date, reason in leave_requests:
        days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
        cur.execute(
            """
            INSERT INTO leave_requests
            (leave_id, employee_id, leave_type, status, start_date, end_date, days, reason)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            ("PENDING", employee_id, leave_type, status, start_date, end_date, days, reason),
        )
        leave_ref = f"LV-{cur.lastrowid:06d}"
        cur.execute("UPDATE leave_requests SET leave_id = ? WHERE id = ?", (leave_ref, cur.lastrowid))

    conn.commit()
    conn.close()
    print(f"Seeded {len(leave_requests)} leave requests.")


if __name__ == "__main__":
    build()
