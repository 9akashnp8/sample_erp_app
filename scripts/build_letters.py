"""
Builds/seeds the letters & certificates module table: letter_requests.
Assumes employees AND the finance tables already exist — issued letters
snapshot salary/bank details, so run build_employees.py and build_finance.py
first (entrypoint.sh already orders them that way).
Re-run any time to reset letter_requests to seed state.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_letters.sql")

# Mirrors app/routers/letters.py — same duplication as fake_encrypt() in
# build_finance.py, and for the same reason: seed scripts stay importable
# stand-alone rather than pulling the FastAPI app in to seed a table.
LETTER_TYPE = "For Whom It May Concern"
LETTER_TYPE_CODE = "FWIMC"


def snapshot_for(cur, employee_id, include_salary, include_bank_details):
    """The details an issued letter freezes. Raises if the data the request
    asked for isn't there — the API returns 400 in exactly that case, so seed
    rows that would be impossible to issue live shouldn't be creatable here."""
    emp = cur.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    values = [f"{emp['first_name']} {emp['last_name']}", emp["job_title"],
              emp["department"], emp["employment_type"], emp["hire_date"]]

    if include_salary:
        salary = cur.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not salary:
            raise RuntimeError(f"No salary_info for {employee_id} — cannot seed an issued "
                               "letter that includes salary details.")
        values += [salary["gross_salary"], salary["currency"], salary["pay_frequency"]]
    else:
        values += [None, None, None]

    if include_bank_details:
        account = cur.execute(
            """SELECT * FROM bank_accounts WHERE employee_id = ? AND status = 'Active'
               ORDER BY is_primary DESC, id LIMIT 1""",
            (employee_id,),
        ).fetchone()
        if not account:
            raise RuntimeError(f"No active bank_account for {employee_id} — cannot seed an "
                               "issued letter that includes bank details.")
        values += [account["bank_name"], account["account_holder_name"],
                   account["masked_account_number"], account["iban"], account["swift_bic"]]
    else:
        values += [None, None, None, None, None]

    return values


def build():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS letter_requests")
    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())

    # Sanity check: employees + finance tables must already exist and be
    # populated. Fail loudly on a missing dependency (build_finance.py's
    # convention) rather than seeding letters that can never be issued.
    try:
        emp_count = cur.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM salary_info").fetchone()
        cur.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()
    except sqlite3.OperationalError:
        raise RuntimeError(
            "employees / finance tables not found. Run scripts/build_employees.py "
            "then scripts/build_finance.py first."
        )
    if emp_count == 0:
        raise RuntimeError("employees table is empty. Run scripts/build_employees.py first.")

    # (employee_id, include_salary, include_bank, addressed_to, purpose,
    #  status, decision_notes, created_at, issued_at)
    #
    # Covers all four statuses and all three variants (plain / +salary /
    # +salary+bank). E-2043 — the running example throughout the README — has
    # two issued letters of different variants plus history to page through.
    # E-1755 is deliberately absent: they are Terminated, and the API refuses
    # a For Whom It May Concern request for them (see README).
    letter_requests = [
        ("E-2043", 0, 0, None, "a rental application",
         "Issued", None, "2026-08-10 09:12:00", "2026-08-11 10:05:00"),
        ("E-2043", 1, 0, "The Consulate General of Canada", "a visitor visa application",
         "Issued", "Standard visa letter.", "2026-08-19 14:30:00", "2026-08-20 08:40:00"),
        ("E-1187", 1, 1, "HDFC Bank Ltd.", "a home loan application",
         "Issued", None, "2026-08-24 11:02:00", "2026-08-25 09:15:00"),
        ("E-3110", 0, 0, "The Admissions Office, Lakeside School", "a school admission",
         "Issued", None, "2026-08-27 16:45:00", "2026-08-28 10:20:00"),
        ("E-2210", 1, 0, None, "a credit card application",
         "Issued", None, "2026-09-01 08:55:00", "2026-09-01 15:30:00"),
        ("E-3320", 1, 0, "Ausländerbehörde Berlin", "a residence permit renewal",
         "Pending", None, "2026-09-04 07:40:00", None),
        ("E-1902", 0, 0, "The British Council", None,
         "Pending", None, "2026-09-05 12:15:00", None),
        ("E-4501", 1, 1, None, "a vehicle loan application",
         "Pending", None, "2026-09-06 09:30:00", None),
        ("E-4890", 0, 0, "The Registrar, State University", "internship verification",
         "Pending", None, "2026-09-07 10:10:00", None),
        ("E-2765", 1, 1, "Kestrel Lettings", "a tenancy application",
         "Rejected", ("Bank details aren't shared with letting agents — please re-submit "
                      "with salary details only."), "2026-08-30 13:20:00", None),
        ("E-2891", 0, 0, None, "a gym membership",
         "Cancelled", None, "2026-08-31 17:05:00", None),
    ]

    for (employee_id, include_salary, include_bank, addressed_to, purpose,
         status, decision_notes, created_at, issued_at) in letter_requests:
        if status == "Issued":
            snapshot = snapshot_for(cur, employee_id, include_salary, include_bank)
        else:
            snapshot = [None] * 13

        cur.execute(
            """
            INSERT INTO letter_requests
            (request_ref, employee_id, letter_type, include_salary, include_bank_details,
             addressed_to, purpose, status, decision_notes, document_ref, issued_at,
             snapshot_full_name, snapshot_job_title, snapshot_department,
             snapshot_employment_type, snapshot_hire_date,
             snapshot_gross_salary, snapshot_currency, snapshot_pay_frequency,
             snapshot_bank_name, snapshot_account_holder_name,
             snapshot_masked_account_number, snapshot_iban, snapshot_swift_bic,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("PENDING", employee_id, LETTER_TYPE, include_salary, include_bank,
             addressed_to, purpose, status, decision_notes, None, issued_at,
             *snapshot, created_at, issued_at or created_at),
        )

        # request_ref/document_ref both derive from the autoincrement id, which
        # SQLite only assigns after the INSERT — same two-step as the API.
        row_id = cur.lastrowid
        request_ref = f"LC-{row_id:06d}"
        document_ref = None
        if status == "Issued":
            document_ref = (f"{LETTER_TYPE_CODE}-{issued_at[:4]}-"
                            f"{employee_id.replace('E-', 'E')}-{row_id:06d}")
        cur.execute(
            "UPDATE letter_requests SET request_ref = ?, document_ref = ? WHERE id = ?",
            (request_ref, document_ref, row_id),
        )

    conn.commit()
    conn.close()
    issued = sum(1 for r in letter_requests if r[5] == "Issued")
    print(f"Seeded {len(letter_requests)} letter requests ({issued} issued).")


if __name__ == "__main__":
    build()
