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
│   │   └── employees.py       # /employees endpoints
│   └── schemas/
│       └── employee.py        # Pydantic request/response models
├── db/
│   ├── schema_employees.sql   # table DDL
│   └── erp.db                 # generated SQLite file (gitignore this)
├── scripts/
│   └── build_employees.py     # (re)creates + seeds the employees table
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

## Using it from agent code

```python
from erp_client import ERPClient

erp = ERPClient()  # reads ERP_BASE_URL env var, defaults to http://localhost:8000

profile = erp.get_employee("E-2043")
team = erp.get_direct_reports("E-3320")
engineers = erp.list_employees(department="Engineering", status="Active")
erp.update_employee("E-2043", department="Sales")
```

To point at a different environment (real ERP, staging, etc.):

```bash
export ERP_BASE_URL=https://real-erp.company.com/api
```

or `ERPClient(base_url="https://real-erp.company.com/api")` explicitly.

## Adding the next module (e.g. leave requests)

1. Add `db/schema_leave.sql` + a `scripts/build_leave.py` seeder.
2. Add `app/schemas/leave.py` (Pydantic models).
3. Add `app/routers/leave.py` (endpoints), same CRUD pattern as `employees.py`.
4. Register it in `app/main.py`: `app.include_router(leave.router)`.
5. Add corresponding methods to `erp_client.py` under a `# ---- Leave module ----` section.

Keeping every module's router + schema + client methods this consistent is
what makes the eventual "swap to the real ERP" a config change instead of a rewrite.
