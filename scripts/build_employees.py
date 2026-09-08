"""
Builds erp.db and seeds the employees table.
Re-run any time to reset to seed state.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
# SCHEMA_DIR defaults to db/ for local runs; the Docker image sets it to a
# path baked into the image (not the persisted-data volume) so schema files
# are never shadowed by a stale volume — see Dockerfile.
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_employees.sql")


def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Drop and recreate for a clean seed
    cur.execute("DROP TABLE IF EXISTS employees")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        cur.executescript(f.read())

    # (employee_id, first, last, email, title, department, manager_id, emp_type, status, hire_date, term_date, location, phone)
    employees = [
        ("E-1000", "Meredith", "Duarte", "meredith.duarte@acmecorp.example", "VP of Engineering", "Engineering", None, "Full-Time", "Active", "2019-03-11", None, "New York", "+1-212-555-0101"),
        ("E-1001", "Sanjay", "Yang", "sanjay.yang@acmecorp.example", "VP of Sales", "Sales", None, "Full-Time", "Active", "2018-07-22", None, "New York", "+1-212-555-0102"),
        ("E-1002", "Renata", "Novak", "renata.novak@acmecorp.example", "Head of HR", "Human Resources", None, "Full-Time", "Active", "2017-01-09", None, "Chicago", "+1-312-555-0103"),

        ("E-2043", "Priya", "Sharma", "priya.sharma@acmecorp.example", "Senior Software Engineer", "Engineering", "E-1000", "Full-Time", "Active", "2021-05-03", None, "New York", "+1-212-555-0201"),
        ("E-1187", "James", "Okoro", "james.okoro@acmecorp.example", "Software Engineer", "Engineering", "E-1000", "Full-Time", "Active", "2022-09-19", None, "Remote", "+1-415-555-0202"),
        ("E-3320", "Lena", "Fischer", "lena.fischer@acmecorp.example", "Engineering Manager", "Engineering", "E-1000", "Full-Time", "Active", "2020-02-17", None, "Berlin", "+49-30-555-0203"),
        ("E-1902", "Aisha", "Khan", "aisha.khan@acmecorp.example", "Product Designer", "Design", "E-3320", "Full-Time", "On Leave", "2021-11-08", None, "London", "+44-20-555-0204"),
        ("E-4501", "Carlos", "Mendez", "carlos.mendez@acmecorp.example", "QA Engineer", "Engineering", "E-3320", "Contractor", "Active", "2023-01-30", None, "Remote", "+1-305-555-0205"),
        ("E-2765", "Tom", "Bennett", "tom.bennett@acmecorp.example", "Account Executive", "Sales", "E-1001", "Full-Time", "Active", "2022-04-12", None, "Chicago", "+1-312-555-0206"),
        ("E-2891", "Fatima", "Al-Sayed", "fatima.alsayed@acmecorp.example", "Sales Development Rep", "Sales", "E-1001", "Full-Time", "Active", "2023-06-05", None, "Remote", "+1-415-555-0207"),
        ("E-3110", "Derek", "Osei", "derek.osei@acmecorp.example", "HR Business Partner", "Human Resources", "E-1002", "Full-Time", "Active", "2021-08-16", None, "Chicago", "+1-312-555-0208"),
        ("E-3502", "Wei", "Zhang", "wei.zhang@acmecorp.example", "Recruiter", "Human Resources", "E-1002", "Full-Time", "Active", "2022-11-01", None, "Remote", "+1-628-555-0209"),
        ("E-2210", "Nora", "Kelleher", "nora.kelleher@acmecorp.example", "Financial Analyst", "Finance", "E-1002", "Full-Time", "Active", "2020-10-05", None, "New York", "+1-212-555-0210"),
        ("E-4890", "Ben", "Whitfield", "ben.whitfield@acmecorp.example", "Software Engineer Intern", "Engineering", "E-3320", "Intern", "Active", "2025-06-01", None, "Remote", "+1-628-555-0211"),
        ("E-1755", "Grace", "Liu", "grace.liu@acmecorp.example", "Former Support Specialist", "Customer Support", "E-1002", "Full-Time", "Terminated", "2019-09-23", "2025-03-14", "Chicago", "+1-312-555-0212"),
    ]

    cur.executemany(
        """
        INSERT INTO employees
        (employee_id, first_name, last_name, email, job_title, department,
         manager_id, employment_type, status, hire_date, termination_date, location, phone)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        employees,
    )

    conn.commit()
    conn.close()
    print(f"Built {DB_PATH} with {len(employees)} employees.")


if __name__ == "__main__":
    build()
