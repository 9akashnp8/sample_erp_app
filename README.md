# Sample ERP App — Employee Module

A minimal FastAPI + SQLite service that stands in for a real ERP so agents
can be built and tested against a stable API shape. When real ERP access is
available, point `ERP_BASE_URL` at it — agent code that uses `erp_client.py`
should not need to change.

## Structure

```
erp_app/
├── app/
│   ├── main.py                # FastAPI entrypoint — register new module routers here
│   ├── database.py            # sqlite3 connection helper
│   ├── routers/
│   │   ├── employees.py       # /employees endpoints
│   │   └── finance.py         # /finance endpoints (bank accounts, salary, payslips)
│   └── schemas/
│       ├── employee.py        # Pydantic request/response models
│       └── finance.py         # Pydantic request/response models
├── db/
│   ├── schema_employees.sql   # employees table DDL
│   ├── schema_finance.sql     # bank_accounts / salary_info / payslips DDL
│   └── erp.db                 # generated SQLite file (gitignore this)
├── scripts/
│   ├── build_employees.py     # (re)creates + seeds the employees table
│   └── build_finance.py       # (re)creates + seeds finance tables (run after build_employees.py)
├── erp_client.py              # <-- agents import THIS, not the DB or routers
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh              # seeds db (if missing) then starts uvicorn
└── requirements.txt
```

## Running it — Docker (recommended)

```bash
docker compose up --build
```

That's it. The container seeds `db/erp.db` on first boot (persisted in a
named volume, so restarts keep your data), then starts the API on
`http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

To force a full reseed back to the 15 sample employees (wipes any changes
made through the API):

```bash
docker compose down -v && docker compose up --build     # -v drops the volume
# or, without dropping the volume:
docker compose run -e RESET_DB=1 erp-api
```

Without Compose, plain Docker works too:

```bash
docker build -t sample-erp .
docker run -p 8000:8000 -v erp-db-data:/app/db sample-erp
```

Point agents at it exactly as before — nothing about `erp_client.py` changes
whether the API is running in Docker or locally:

```bash
export ERP_BASE_URL=http://localhost:8000
```

## Running it — local Python (no Docker)

```bash
pip install -r requirements.txt
python scripts/build_employees.py     # builds db/erp.db with 15 seed employees
python scripts/build_finance.py       # seeds bank accounts, salary, payslips (run after the above)
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs


## Employee table

`employees`: `id, employee_id (unique, e.g. E-2043), first_name, last_name,
email, job_title, department, manager_id (self-FK), employment_type
(Full-Time/Part-Time/Contractor/Intern), status (Active/On Leave/Terminated),
hire_date, termination_date, location, phone, created_at, updated_at`

Seed data: 15 employees across Engineering, Sales, HR, Finance, Design, and
Customer Support, in a 3-level reporting hierarchy (execs → managers → ICs),
including one `On Leave` and one `Terminated` employee for edge-case testing.

## Endpoints

| Method | Path                                | Purpose |
|--------|--------------------------------------|---------|
| GET    | `/employees`                        | List/search — filters: `department`, `status`, `manager_id`, `q` (name/email) |
| GET    | `/employees/{employee_id}`          | Fetch one profile |
| GET    | `/employees/{employee_id}/direct-reports` | List direct reports of a manager |
| POST   | `/employees`                        | Onboard new employee |
| PATCH  | `/employees/{employee_id}`          | Partial update (promote, transfer, terminate, etc.) |
| DELETE | `/employees/{employee_id}`          | Hard delete (test cleanup — prefer PATCH status=Terminated) |
| GET    | `/health`                           | Liveness check |

Validation already in place: duplicate `employee_id`/`email` → 409, unknown
`manager_id` on create/update → 400, unknown `employee_id` on read/update/delete → 404.

## Finance module

Three tables, seeded for all 15 employees (bank accounts + salary) and for
the 13 `Active` employees (payslips — 3 months of history each, Apr–Jun 2026):

- **`bank_accounts`** — one or more per employee. The API only ever returns
  a `masked_account_number` (e.g. `****4821`). The full number is "encrypted"
  (a placeholder hash, not real crypto — swap for a KMS call in production)
  and stored in `encrypted_account_number`, which is **never** included in
  any API response — the Pydantic response model excludes the field entirely,
  so this is enforced at the schema level, not just by convention.
- **`salary_info`** — one active record per employee: `gross_salary`,
  `currency`, `pay_frequency`, `effective_date`.
- **`payslips`** — one per employee per period (`period_month`/`period_year`),
  generated from `salary_info` at creation time. `gross_salary` is snapshotted
  onto the payslip so later raises don't retroactively change historical payslips.

| Method | Path                                  | Purpose |
|--------|----------------------------------------|---------|
| GET    | `/finance/bank-accounts`               | List accounts — filter by `employee_id`, `status` |
| GET    | `/finance/bank-accounts/{id}`          | Fetch one account |
| POST   | `/finance/bank-accounts`               | Add an account (masks + "encrypts" the raw number) |
| PATCH  | `/finance/bank-accounts/{id}`          | Update; re-masks if `account_number` supplied |
| DELETE | `/finance/bank-accounts/{id}`          | Hard delete (test cleanup — prefer status=Inactive) |
| GET    | `/finance/salary/{employee_id}`        | Fetch current salary record |
| POST   | `/finance/salary`                      | Create initial salary record (409 if one exists) |
| PATCH  | `/finance/salary/{employee_id}`        | Update salary (e.g. a raise) |
| GET    | `/finance/payslips`                    | List — filter by `employee_id`, `period_year`, `period_month` |
| GET    | `/finance/payslips/{payslip_ref}`      | Fetch one payslip |
| POST   | `/finance/payslips/generate`           | Generate from current salary (409 if one exists for that period, 400 if no salary record) |
| DELETE | `/finance/payslips/{payslip_ref}`      | Hard delete (test cleanup) |

Business rules enforced by the API (not just the seed data):
- Setting `is_primary=true` on a new/updated bank account automatically
  un-sets any other primary account for that employee.
- A payslip can't be generated twice for the same employee + period (409).
- A payslip can't be generated for an employee with no salary record yet (400).

## Using it from agent code

```python
from erp_client import ERPClient

erp = ERPClient()  # reads ERP_BASE_URL env var, defaults to http://localhost:8000

profile = erp.get_employee("E-2043")
team = erp.get_direct_reports("E-3320")
engineers = erp.list_employees(department="Engineering", status="Active")
erp.update_employee("E-2043", department="Sales")

accounts = erp.get_bank_accounts("E-2043")          # masked numbers only
salary = erp.get_salary_info("E-2043")
erp.update_salary_info("E-2043", gross_salary=13000)  # give a raise
payslip = erp.generate_payslip("E-2043", period_month=7, period_year=2026)
history = erp.list_payslips(employee_id="E-2043")
```

To point at a different environment (real ERP, staging, etc.):

```bash
export ERP_BASE_URL=https://real-erp.company.com/api
```

or `ERPClient(base_url="https://real-erp.company.com/api")` explicitly.

## Adding the next module (e.g. leave requests)

1. Add `db/schema_leave.sql` + a `scripts/build_leave.py` seeder (call it after `build_employees.py`, same pattern as `build_finance.py`).
2. Add `app/schemas/leave.py` (Pydantic models).
3. Add `app/routers/leave.py` (endpoints), same CRUD pattern as `employees.py`/`finance.py`.
4. Register it in `app/main.py`: `app.include_router(leave.router)`.
5. Add corresponding methods to `erp_client.py` under a `# ---- Leave module ----` section.
6. Add the new seed script to `entrypoint.sh`'s seeding block.

Keeping every module's router + schema + client methods this consistent is
what makes the eventual "swap to the real ERP" a config change instead of a rewrite.
