"""
Builds/seeds the finance module tables: bank_accounts, salary_info, payslips.
Assumes employees table already exists (run build_employees.py first).
Re-run any time to reset finance tables to seed state.
"""
import sqlite3
import os
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_finance.sql")


def fake_encrypt(raw: str) -> str:
    """Placeholder 'encryption' — NOT real crypto. Stands in for wherever a
    real ERP would store a properly encrypted account number. Swap this for
    an actual encryption call (e.g. via a KMS) when connecting to production."""
    return "enc_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS payslips")
    cur.execute("DROP TABLE IF EXISTS salary_info")
    cur.execute("DROP TABLE IF EXISTS bank_accounts")
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

    # ---------------- bank_accounts ----------------
    # (employee_id, bank_name, holder_name, full_account_number, iban, swift, currency)
    bank_seed = [
        ("E-1000", "Chase Bank",        "Meredith Duarte", "0043829471", "US64CHAS0043829471", "CHASUS33", "USD"),
        ("E-1001", "Bank of America",   "Sanjay Yang",      "0091238845", "US12BOFA0091238845", "BOFAUS3N", "USD"),
        ("E-1002", "Wells Fargo",       "Renata Novak",     "0055627193", "US88WFBI0055627193", "WFBIUS6S", "USD"),
        ("E-2043", "Chase Bank",        "Priya Sharma",     "0038210094", "US25CHAS0038210094", "CHASUS33", "USD"),
        ("E-1187", "Ally Bank",         "James Okoro",      "0071144820", "US45ALLY0071144820", "ALLYUS31", "USD"),
        ("E-3320", "Deutsche Bank",     "Lena Fischer",     "DE7350010517", "DE753001051770001234", "DEUTDEFF", "EUR"),
        ("E-1902", "Barclays",          "Aisha Khan",       "GB2920065812", "GB29BARC20065812345678", "BARCGB22", "GBP"),
        ("E-4501", "Chase Bank",        "Carlos Mendez",    "0062910038", "US19CHAS0062910038", "CHASUS33", "USD"),
        ("E-2765", "Wells Fargo",       "Tom Bennett",      "0084472910", "US61WFBI0084472910", "WFBIUS6S", "USD"),
        ("E-2891", "Bank of America",   "Fatima Al-Sayed",  "0029384710", "US33BOFA0029384710", "BOFAUS3N", "USD"),
        ("E-3110", "Chase Bank",        "Derek Osei",       "0074829103", "US77CHAS0074829103", "CHASUS33", "USD"),
        ("E-3502", "Ally Bank",         "Wei Zhang",        "0018475920", "US52ALLY0018475920", "ALLYUS31", "USD"),
        ("E-2210", "Chase Bank",        "Nora Kelleher",    "0093820174", "US14CHAS0093820174", "CHASUS33", "USD"),
        ("E-4890", "Wells Fargo",       "Ben Whitfield",    "0067281940", "US36WFBI0067281940", "WFBIUS6S", "USD"),
        ("E-1755", "Bank of America",   "Grace Liu",        "0051029384", "US82BOFA0051029384", "BOFAUS3N", "USD"),
    ]

    for emp_id, bank, holder, full_acct, iban, swift, currency in bank_seed:
        masked = "****" + full_acct[-4:]
        encrypted = fake_encrypt(full_acct)
        cur.execute(
            """
            INSERT INTO bank_accounts
            (employee_id, bank_name, account_holder_name, masked_account_number,
             encrypted_account_number, iban, swift_bic, currency, is_primary, status)
            VALUES (?,?,?,?,?,?,?,?,1,'Active')
            """,
            (emp_id, bank, holder, masked, encrypted, iban, swift, currency),
        )

    # ---------------- salary_info ----------------
    # Gross monthly salary roughly reflecting seniority; currency matches each
    # employee's home-country bank account above for a touch of realism.
    salary_seed = [
        ("E-1000", 18500, "USD", "2019-03-11"),
        ("E-1001", 17800, "USD", "2018-07-22"),
        ("E-1002", 15200, "USD", "2017-01-09"),
        ("E-2043", 11200, "USD", "2021-05-03"),
        ("E-1187",  8600,  "USD", "2022-09-19"),
        ("E-3320", 13400, "EUR", "2020-02-17"),
        ("E-1902",  7900,  "GBP", "2021-11-08"),
        ("E-4501",  6800,  "USD", "2023-01-30"),
        ("E-2765",  7200,  "USD", "2022-04-12"),
        ("E-2891",  5400,  "USD", "2023-06-05"),
        ("E-3110",  8100,  "USD", "2021-08-16"),
        ("E-3502",  6900,  "USD", "2022-11-01"),
        ("E-2210",  7600,  "USD", "2020-10-05"),
        ("E-4890",  3200,  "USD", "2025-06-01"),
        ("E-1755",  5800,  "USD", "2019-09-23"),
    ]

    cur.executemany(
        """
        INSERT INTO salary_info (employee_id, gross_salary, currency, pay_frequency, effective_date)
        VALUES (?,?,?, 'Monthly', ?)
        """,
        salary_seed,
    )

    # ---------------- payslips ----------------
    # Generate 3 months of history (Apr, May, Jun 2026) for active employees only.
    # Simple flat tax approximation for sample data: 18% tax, small fixed "other" deduction.
    active_employees = cur.execute(
        "SELECT employee_id, status FROM employees"
    ).fetchall()
    active_ids = {row[0] for row in active_employees if row[1] == "Active"}

    salary_lookup = {row[0]: (row[1], row[2]) for row in
                      cur.execute("SELECT employee_id, gross_salary, currency FROM salary_info").fetchall()}

    periods = [(4, 2026), (5, 2026), (6, 2026)]
    TAX_RATE = 0.18
    OTHER_DEDUCTION = 120.0  # flat sample "benefits" deduction

    payslip_count = 0
    for emp_id in sorted(active_ids):
        if emp_id not in salary_lookup:
            continue
        gross, currency = salary_lookup[emp_id]
        for month, year in periods:
            tax = round(gross * TAX_RATE, 2)
            other = OTHER_DEDUCTION
            net = round(gross - tax - other, 2)
            ref = f"PS-{year}-{month:02d}-{emp_id.replace('E-', 'E')}"
            cur.execute(
                """
                INSERT INTO payslips
                (payslip_ref, employee_id, period_month, period_year, gross_salary,
                 tax_deduction, other_deductions, other_deductions_note, net_pay,
                 currency, status, generated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?, 'Generated', datetime('now'))
                """,
                (ref, emp_id, month, year, gross, tax, other, "Standard benefits deduction", net, currency),
            )
            payslip_count += 1

    conn.commit()
    conn.close()
    print(f"Seeded {len(bank_seed)} bank accounts, {len(salary_seed)} salary records, "
          f"{payslip_count} payslips.")


if __name__ == "__main__":
    build()
