"""
Builds/seeds the helpdesk module table: tickets.
Assumes employees table already exists (run build_employees.py first).
Re-run any time to reset the tickets table to seed state.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_helpdesk.sql")


def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS tickets")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
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

    # (subject, description, requester_id, assignee_id, category, priority, status,
    #  resolved_at, closed_at, created_at)
    # resolved_at/closed_at are seeded directly for Resolved/Closed rows so seed
    # data stays consistent with the rules the API enforces on PATCH.
    tickets = [
        ("VPN keeps disconnecting", "My VPN drops every 20 minutes while working remotely.",
         "E-1187", "E-4501", "IT", "High", "In Progress", None, None, "2026-06-02 09:15:00"),
        ("Laptop won't boot", "Screen stays black after the last OS update.",
         "E-2765", "E-4501", "IT", "Urgent", "Open", None, None, "2026-06-10 14:02:00"),
        ("Request access to Finance drive", "Need read access to the shared Finance drive for Q3 planning.",
         "E-2210", None, "IT", "Medium", "Open", None, None, "2026-06-11 08:40:00"),
        ("Payslip discrepancy", "June payslip shows the wrong tax deduction amount.",
         "E-4890", "E-3110", "Finance", "High", "In Progress", None, None, "2026-06-12 11:20:00"),
        ("Update banking details", "Need to update my primary bank account for payroll.",
         "E-2891", "E-3110", "Finance", "Medium", "Resolved", "2026-06-14 16:05:00", None, "2026-06-13 10:00:00"),
        ("Broken office chair", "Chair at desk 14B has a broken armrest.",
         "E-3502", "E-1002", "Facilities", "Low", "Open", None, None, "2026-06-15 13:30:00"),
        ("AC not working on 3rd floor", "It's been unusually warm on the 3rd floor since Monday.",
         "E-1755", None, "Facilities", "Medium", "Open", None, None, "2026-06-16 09:00:00"),
        ("Onboarding laptop request", "New hire starting July 1st needs a laptop provisioned.",
         "E-3110", "E-4501", "IT", "High", "Resolved", "2026-06-20 12:00:00", None, "2026-06-17 15:45:00"),
        ("Benefits enrollment question", "Not sure which health plan tier I'm currently enrolled in.",
         "E-1902", "E-3110", "HR", "Low", "Closed", "2026-06-19 10:00:00", "2026-06-19 10:05:00", "2026-06-18 08:20:00"),
        ("Expense report rejected", "My expense report for the client dinner was rejected without a reason.",
         "E-2891", "E-2210", "Finance", "Medium", "In Progress", None, None, "2026-06-19 17:10:00"),
        ("Password reset for shared inbox", "Need the password reset for the support@ shared inbox.",
         "E-4501", None, "IT", "Low", "Open", None, None, "2026-06-21 09:05:00"),
        ("Slow wifi in conference room B", "Video calls keep freezing in conference room B.",
         "E-3320", "E-4501", "IT", "Medium", "Closed", "2026-06-22 14:00:00", "2026-06-22 14:30:00", "2026-06-20 11:00:00"),
        ("Parking badge not working", "My parking badge stopped working at the garage entrance.",
         "E-2765", "E-1002", "Facilities", "Low", "Open", None, None, "2026-06-23 08:15:00"),
        ("Time-off balance looks wrong", "PTO balance dropped by 5 days but I haven't taken any leave.",
         "E-1187", "E-3110", "HR", "High", "Open", None, None, "2026-06-24 10:30:00"),
    ]

    for (subject, description, requester_id, assignee_id, category, priority, status,
         resolved_at, closed_at, created_at) in tickets:
        cur.execute(
            """
            INSERT INTO tickets
            (ticket_id, subject, description, requester_id, assignee_id, category,
             priority, status, resolved_at, closed_at, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("PENDING", subject, description, requester_id, assignee_id, category,
             priority, status, resolved_at, closed_at, created_at, created_at),
        )
        ticket_ref = f"TCK-{cur.lastrowid:06d}"
        cur.execute("UPDATE tickets SET ticket_id = ? WHERE id = ?", (ticket_ref, cur.lastrowid))

    conn.commit()
    conn.close()
    print(f"Seeded {len(tickets)} tickets.")


if __name__ == "__main__":
    build()
