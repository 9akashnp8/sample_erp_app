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
│   │   ├── finance.py         # /finance endpoints (bank accounts, salary, payslips)
│   │   └── helpdesk.py        # /tickets endpoints + outbound webhook dispatch
│   └── schemas/
│       ├── employee.py        # Pydantic request/response models
│       ├── finance.py         # Pydantic request/response models
│       └── helpdesk.py        # Pydantic request/response models
├── db/
│   ├── schema_employees.sql   # employees table DDL
│   ├── schema_finance.sql     # bank_accounts / salary_info / payslips DDL
│   ├── schema_helpdesk.sql    # tickets table DDL
│   └── erp.db                 # generated SQLite file (gitignore this)
├── scripts/
│   ├── build_employees.py     # (re)creates + seeds the employees table
│   ├── build_finance.py       # (re)creates + seeds finance tables (run after build_employees.py)
│   └── build_helpdesk.py      # (re)creates + seeds tickets (run after build_employees.py)
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
python scripts/build_helpdesk.py      # seeds tickets (run after the above)
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

## Helpdesk module

`tickets`: `id, ticket_id (unique, server-generated e.g. TCK-000042), subject,
description, requester_id (FK -> employees), assignee_id (FK -> employees,
nullable), category, priority (Low/Medium/High/Urgent), status (Open/In
Progress/Resolved/Closed), resolved_at, closed_at, created_at, updated_at`.

There's no separate user/auth system in this app — employees *are* the
users, so `requester_id`/`assignee_id` are just employee_ids, same as
`manager_id` on the employee table.

Unlike every other status-like field in this app (plain `str` with a
comment), `status` and `priority` use Pydantic `Literal[...]` types. This is
a deliberate, narrowly-scoped deviation: these values drive an outbound
webhook to an external agent app (see below), so invalid values should 422
at the API boundary instead of silently propagating downstream. `category`
stays plain `str` (open-ended, like `department`). A ticket's initial
`status` is never caller-suppliable — it's always created as `Open`
server-side, so every real status transition goes through `PATCH` and is
guaranteed to fire the `ticket.status_changed` webhook event.

Seed data: 14 sample tickets across IT/Finance/Facilities/HR, spanning all
four statuses and priorities, several left unassigned.

| Method | Path                        | Purpose |
|--------|-----------------------------|---------|
| GET    | `/tickets`                  | List/search — filters: `status`, `priority`, `category`, `requester_id`, `assignee_id`, `q` (subject/description) |
| GET    | `/tickets/{ticket_id}`      | Fetch one ticket |
| POST   | `/tickets`                  | File a new ticket (always created as `status=Open`) |
| PATCH  | `/tickets/{ticket_id}`      | Partial update — reassign, change priority/category, change status |
| DELETE | `/tickets/{ticket_id}`      | Hard delete (test cleanup — prefer PATCH `status=Closed`) |

Business rules enforced by the API:
- Unknown `requester_id`/`assignee_id` → 404/400 as appropriate; `assignee_id`
  can be `null` (unassigned).
- `requester_id` is immutable after creation (not settable via PATCH).
- Setting `status=Resolved` stamps `resolved_at`. Setting `status=Closed`
  stamps `closed_at`, and backfills `resolved_at` too if the ticket skipped
  straight from `Open`/`In Progress` to `Closed`.
- Reopening a ticket (moving status away from `Resolved`/`Closed`) does
  **not** clear `resolved_at`/`closed_at` — that history is preserved.

### Webhook dispatch

When `TICKET_WEBHOOK_URL` is set (env var), the API synchronously `POST`s a
JSON event to it right after each successful ticket write — meant for a
separate, external agentic app to react to ticket activity. If the env var
is unset, dispatch is a no-op (default for local/Docker runs). This is a
best-effort, fire-and-forget call (stdlib `urllib.request`, ~3s timeout,
failures are logged and swallowed) — there's no retry queue or outbox, by
design, to keep this sample app simple. `DELETE` never fires a webhook
(it's test-cleanup only, not a real ticket lifecycle event).

Events:
- `ticket.created` — fired once on `POST /tickets`.
- `ticket.status_changed` — fired on `PATCH` when `status` changes.
- `ticket.assigned` — fired on `PATCH` when `assignee_id` changes (including
  to/from `null` for assign/unassign).

A single `PATCH` that changes both `status` and `assignee_id` fires two
separate webhook calls.

Payload shape:
```json
{
  "event": "ticket.created | ticket.status_changed | ticket.assigned",
  "timestamp": "2026-07-25 14:03:11",
  "ticket": { "...full ticket object, same shape as GET /tickets/{id}..." },
  "changes": { "status": {"old": "Open", "new": "In Progress"} }
}
```
`changes` is present only for `ticket.status_changed` (key: `status`) and
`ticket.assigned` (key: `assignee_id`); absent for `ticket.created`.

Optional `TICKET_WEBHOOK_SECRET` env var, if set, is sent as an
`X-Webhook-Secret` header — the receiving app should do a constant-time
compare against its own copy of the secret. HMAC-signing the body would be
the natural v2 hardening if this is ever exposed on a public endpoint, but
is out of scope for this sample.

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

ticket = erp.create_ticket("VPN drops constantly", "Disconnects every 20 min.",
                            requester_id="E-1187", category="IT", priority="High")
erp.assign_ticket(ticket["ticket_id"], assignee_id="E-4501")
erp.resolve_ticket(ticket["ticket_id"])
open_tickets = erp.list_tickets(status="Open", assignee_id="E-4501")
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
