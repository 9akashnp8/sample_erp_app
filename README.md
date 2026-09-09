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
│   ├── pdf_writer.py          # tiny stdlib-only PDF writer (issued letters)
│   ├── routers/
│   │   ├── employees.py       # /employees endpoints
│   │   ├── finance.py         # /finance endpoints (bank accounts, salary, payslips)
│   │   ├── helpdesk.py        # /tickets endpoints + outbound webhook dispatch
│   │   ├── leave.py           # /leave-requests endpoints
│   │   ├── letters.py         # /letters endpoints (For Whom It May Concern requests + PDF)
│   │   └── performance.py     # /performance endpoints (review workflow, objectives, appraisals)
│   └── schemas/
│       ├── employee.py        # Pydantic request/response models
│       ├── finance.py         # Pydantic request/response models
│       ├── helpdesk.py        # Pydantic request/response models
│       ├── leave.py           # Pydantic request/response models
│       ├── letters.py         # Pydantic request/response models
│       └── performance.py     # Pydantic request/response models
├── db/
│   ├── schema_employees.sql   # employees table DDL
│   ├── schema_finance.sql     # bank_accounts / salary_info / payslips DDL
│   ├── schema_helpdesk.sql    # tickets table DDL
│   ├── schema_leave.sql       # leave_requests table DDL
│   ├── schema_letters.sql     # letter_requests table DDL
│   ├── schema_performance.sql # competencies / performance_reviews / objectives / competency ratings DDL
│   └── erp.db                 # generated SQLite file (gitignore this)
├── scripts/
│   ├── build_employees.py     # (re)creates + seeds the employees table
│   ├── build_finance.py       # (re)creates + seeds finance tables (run after build_employees.py)
│   ├── build_helpdesk.py      # (re)creates + seeds tickets (run after build_employees.py)
│   ├── build_leave.py         # (re)creates + seeds leave requests (run after build_employees.py)
│   ├── build_letters.py       # (re)creates + seeds letter requests (run after build_finance.py)
│   └── build_performance.py   # (re)creates + seeds performance reviews (run after build_employees.py)
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

Only `erp.db` itself lives in that named volume — the `db/schema_*.sql`
files are copied into the image at `/app/schema` (`SCHEMA_DIR` env var, set
in the Dockerfile) rather than into the volume-mounted `/app/db`. This
matters because a named volume is only auto-populated from the image on its
*first* creation; if schema files lived inside it, adding a new module's
schema file to a later image would get permanently shadowed by an
already-existing volume from an older build, and even `RESET_DB=1` wouldn't
surface it (it reseeds from whatever's in `/app/db`, which the volume has
frozen). Keeping schema files outside the volume means a plain rebuild +
reseed is always enough — you should only need to drop the volume to wipe
actual data, not to pick up schema changes.

To force a full reseed back to the sample data (wipes any changes made
through the API):

```bash
docker compose run -e RESET_DB=1 erp-api
```

Or, to also wipe the volume entirely (e.g. after changing `docker-compose.yml`'s
`environment:` block, or if you suspect the volume predates this schema/data
separation):

```bash
docker compose down -v && docker compose up --build     # -v drops the volume
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
python scripts/build_leave.py         # seeds leave requests (run after the above; finance depends on this for payslip generation)
python scripts/build_letters.py       # seeds letter requests (run after the above; issued letters snapshot salary/bank data)
python scripts/build_performance.py   # seeds competencies + performance reviews (run after the above)
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

### Windows (no Docker, no Postgres needed)

The app is backed by SQLite (`app/database.py`), not Postgres — a local
Postgres server, if you have one running, is not used by anything here.
`entrypoint.sh` and the volume mounts in `docker-compose.yml` are
Docker-only conveniences; running natively just means doing what that
script does, by hand, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\build_employees.py
.venv\Scripts\python.exe scripts\build_finance.py
.venv\Scripts\python.exe scripts\build_helpdesk.py
.venv\Scripts\python.exe scripts\build_leave.py
.venv\Scripts\python.exe scripts\build_performance.py
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

On a network with TLS-inspecting proxies, `pip install` may need to trust
the proxy's own hosts explicitly (the same issue the Dockerfile works
around by installing a corporate CA):

```powershell
.venv\Scripts\python.exe -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org -r requirements.txt
```

To reseed later, re-run the `build_*.py` scripts (they drop and recreate
their own tables) or just delete `db\erp.db` and run all five again.


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
  Also carries `unpaid_leave_days` and `leave_deduction` — see "Leave module"
  below for how these are computed. `net_pay = gross - tax - other - leave_deduction`.

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
- Generating a payslip looks up `Unpaid` + `Approved` leave requests (see the
  Leave module below) for that employee whose `start_date` falls in the
  requested period, and deducts `(gross_salary / WORKING_DAYS_PER_MONTH) *
  unpaid_days` from `net_pay`. `WORKING_DAYS_PER_MONTH = 22` is a flat sample
  assumption (same style as the flat 18% `TAX_RATE`) — no real working-day
  calendar is modeled. A leave request is attributed entirely to the month
  its `start_date` falls in; a request whose `end_date` crosses into the next
  month is **not** split/prorated across two payslips. This is now a hard
  dependency — `finance` requires the `leave_requests` table to exist (i.e.
  `build_leave.py` must have run), and will error rather than silently
  degrade if it hasn't, consistent with how every other module here fails
  loudly on a missing dependency rather than gracefully falling back.

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

## Leave module

`leave_requests`: `id, leave_id (unique, server-generated e.g. LV-000012),
employee_id (FK -> employees), leave_type (Annual/Sick/Unpaid/Other), status
(Approved/Rejected/Cancelled), start_date, end_date, days (server-computed,
calendar days inclusive of both endpoints), reason, created_at, updated_at`.

Two things about this module deliberately differ from Helpdesk's ticket
workflow:
- **No approval workflow.** There's no separate approver role modeled in
  this app, so a leave request is created already in its final state —
  `status` is *required* on create (unlike a ticket's status, which is
  always server-forced to `Open`). The caller states the real-world outcome
  directly.
- **`leave_type`/`status` use `Literal[...]`**, like tickets — but for a
  different reason. There's no webhook here; instead, `finance.py`'s payslip
  generation does an exact string match on `leave_type == "Unpaid"` and
  `status == "Approved"` to compute a salary deduction (see Finance module
  above), so a typo'd value needs to 422 at the API boundary rather than
  silently break that match.

No overlap validation: two `Approved`+`Unpaid` requests for the same
employee covering the same dates will double-count in the payslip deduction
(`SUM(days)`) — not enforced at the DB/API level, same minimalism as
`bank_accounts` allowing multiple accounts per employee with no overlap
concept. Also **not** wired up: `leave_requests.status` has no automation
with the existing `employees.status = 'On Leave'` value — they're
independent.

Seed data: 14 sample leave requests across all employees/types/statuses,
including several `Unpaid`+`Approved` requests dated in July 2026 (for
`E-2043` among others) so generating a July payslip demonstrates the
deduction — see "Using it from agent code" below.

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| GET    | `/leave-requests`                 | List/search — filters: `employee_id`, `leave_type`, `status`, `period_year`+`period_month` (matches `start_date`) |
| GET    | `/leave-requests/{leave_id}`      | Fetch one leave request |
| POST   | `/leave-requests`                 | Create a leave request (status required — no workflow) |
| PATCH  | `/leave-requests/{leave_id}`      | Partial update — status, dates, type, reason |
| DELETE | `/leave-requests/{leave_id}`      | Hard delete (test cleanup) |

Business rules enforced by the API:
- Unknown `employee_id` → 404. `employee_id` is immutable after creation.
- `end_date` must be on or after `start_date` (400 otherwise), on both
  create and update.
- `days` is never caller-supplied — always computed server-side from
  `start_date`/`end_date`, and recomputed on any `PATCH` that changes either.

## Letters & certificates module

The self-service side of an HR portal: an employee requests an official
letter, HR issues it, and a formatted PDF comes back. One document type is
modeled so far — **For Whom It May Concern**.

`letter_requests`: `id, request_ref (unique, server-generated e.g. LC-000012),
employee_id (FK -> employees), letter_type, include_salary,
include_bank_details, addressed_to, purpose, status
(Pending/Issued/Rejected/Cancelled), decision_notes, document_ref (assigned at
issue), issued_at, snapshot_* (13 columns, frozen at issue), created_at,
updated_at`.

### The three variants

What goes in the letter is the whole point of the feature:

| `include_salary` | `include_bank_details` | The letter says |
|---|---|---|
| `false` | `false` | Employment only — name, employee id, job title, department, hire date, employment type |
| `true`  | `false` | ...plus the gross salary, currency and pay frequency, read from `salary_info` |
| `true`  | `true`  | ...plus the bank account the salary is credited to, read from `bank_accounts` |

`include_bank_details` without `include_salary` is a **422** — the bank
paragraph exists to say where *that salary* is credited, and the real ERP's
form gates the bank checkbox behind the salary one. It's enforced three
times over (Pydantic validator, a router check on `PATCH`, and a `CHECK`
constraint in the DDL) so no path can write the combination.

### Workflow

```
                         ┌── issue ──► Issued ──► PDF available at .../document
Pending (on create) ─────┼── reject ─► Rejected  (reason required)
                         └── cancel ─► Cancelled (employee withdraws)
```

`status` is never caller-settable — same rule as tickets and performance
reviews, the opposite of leave requests. Every action requires `Pending` and
returns **409** from anywhere else; there is no un-issue, because once a
letter exists it has left the building.

**Issuing is what creates the document.** At that moment the employee's
details (plus salary/bank, if requested) are snapshotted onto the request and
a `document_ref` is assigned. The PDF is then rendered *on demand from that
snapshot*, never stored and never re-read from live tables — so a raise, a
promotion or a new bank account after issue does not silently change a letter
that has already been handed to an embassy. Same reasoning as
`payslips.gross_salary`, and easy to see for yourself:

```python
letter = erp.get_letter_content(ref)      # salary: 11200
erp.update_salary_info("E-2043", gross_salary=99999)
erp.get_letter_content(ref)               # still 11200
```

### The PDF

`app/pdf_writer.py` is a ~150-line stdlib-only PDF writer — no reportlab, no
new dependency, and requirements.txt still has three lines. It produces a real
single- (or multi-) page PDF using the base-14 Helvetica faces, which every
reader ships, so nothing is embedded. Text is WinAnsi (cp1252) encoded, so
Latin-1 names and addressees (`Ausländerbehörde Berlin`) print correctly.

Two ways to read an issued letter, both built from the same composed
document so they can't drift:

- `GET .../document` — the PDF itself (`application/pdf`, with a
  `Content-Disposition` filename of `{document_ref}.pdf`). What the employee
  downloads.
- `GET .../content` — the same letter as JSON: every field plus `body`, the
  paragraphs verbatim. **Agents should read this one** rather than parsing PDF
  bytes.

| Method | Path                                       | Purpose |
|--------|--------------------------------------------|---------|
| GET    | `/letters/requests`                        | List/search — filters: `employee_id`, `status`, `letter_type` |
| GET    | `/letters/requests/{request_ref}`          | Fetch one request |
| POST   | `/letters/requests`                        | Submit a request (always created `Pending`) |
| PATCH  | `/letters/requests/{request_ref}`          | Amend a `Pending` request (409 afterwards) |
| POST   | `/letters/requests/{request_ref}/issue`    | HR — snapshot the details, assign `document_ref`, mark `Issued` |
| POST   | `/letters/requests/{request_ref}/reject`   | HR — decline (`reason` required) |
| POST   | `/letters/requests/{request_ref}/cancel`   | Employee — withdraw a `Pending` request |
| GET    | `/letters/requests/{request_ref}/content`  | The issued letter as JSON (fields + paragraphs) |
| GET    | `/letters/requests/{request_ref}/document` | The issued letter as a PDF |
| DELETE | `/letters/requests/{request_ref}`          | Hard delete (test cleanup) |

Business rules enforced by the API:
- Unknown `employee_id` → 404. `employee_id` and `letter_type` are immutable
  after creation — re-request rather than mutating what was asked for.
- A **`Terminated` employee → 400**, on create and on issue. This letter
  certifies *current* employment; what a leaver needs is an experience letter,
  which this module doesn't model yet. (`E-1755` in the seed data is the case
  to test against.) `On Leave` employees are fine.
- Issuing a letter whose data isn't there → 400: `include_salary` with no
  `salary_info` row, or `include_bank_details` with no `Active` bank account.
  The primary account is used when there's more than one.
- The letter prints the **masked** account number (`****4820`), because this
  app never exposes a full one (see the Finance module). A real letter would
  print the full number — that's the mock-only difference to swap out.

Seed data: 11 requests across all four statuses and all three variants,
including two issued letters for `E-2043`. Currency and Latin-1 coverage come
along for free from the finance seed — `E-3320` is a `EUR` salary addressed to
a German authority, `E-1902` is `GBP`.

## Performance management module

Four tables: `competencies` (pre-defined company core competencies — read-only
reference data), `performance_reviews` (one per employee per cycle year),
`performance_objectives` and `performance_competency_ratings` (both children of
a review, cascade-deleted with it).

This is the first module here with a **real approval workflow** — the opposite
choice from Leave, where a request is created already in its final state. A
review's `status` is never caller-suppliable: it starts at `Draft` and only
moves via the workflow endpoints, each of which refuses to run from the wrong
state (`409`). That state machine *is* the module.

```
Objective Setting stage                         Appraisal stage              Done
────────────────────────────────                ─────────────────────────    ─────────
Draft ──submit-objectives──► Objectives Submitted
                                   │
        ┌──────────────────────────┴──────────────────────────┐
   review-objectives                                   review-objectives
   decision="Send Back"                                decision="Approve"
        │                                                     │
        ▼                                                     ▼
Objectives Sent Back ──submit-objectives──► (back to Submitted)
                                                       Objectives Approved
                                                              │  self-assessment
                                                              ▼
                                                  Self Assessment Submitted
                                                              │  manager-assessment
                                                              ▼
                                                          Completed
```

`stage` (`Objective Setting` / `Appraisal` / `Completed`) is returned on every
review but is **not stored** — it's derived from `status` in the router, so the
two can't drift. You can filter by either (`?stage=Appraisal` expands back into
the statuses it covers).

### Objective setting phase

1. The employee adds objectives — a description plus a `weightage` — one at a
   time via `POST /performance/reviews/{ref}/objectives`. The running total is
   deliberately *not* validated here; objectives are added incrementally.
2. `POST .../submit-objectives` sends them to the manager. **This** is where the
   weightages must total exactly `100` (`400` otherwise, with the actual total in
   the message) and at least one objective must exist. Enforcing it here is what
   lets the appraisal-phase weighted score come out on a plain 1–5 scale.
3. The manager calls `POST .../review-objectives` with `decision: "Approve"` or
   `decision: "Send Back"`. `notes` is **required** on a send-back and optional
   on approve; either way it overwrites `objectives_manager_notes` (approving
   with no notes deliberately clears a stale send-back reason). A sent-back
   review goes back to being editable and can be re-submitted.
4. Once approved, the objective set is frozen — `POST`/`PATCH`/`DELETE` on
   objectives all `409` from `Objectives Approved` onward. That's what makes the
   frozen scores below meaningful.

### Appraisal phase

Both sides rate the same two things — every objective and every **active**
competency — on a 1–5 scale with optional notes, through two endpoints that take
an identical payload and differ only in which columns they write:

- `POST /performance/reviews/{ref}/self-assessment` → writes `self_rating` /
  `self_notes`, requires status `Objectives Approved`, moves to
  `Self Assessment Submitted`.
- `POST /performance/reviews/{ref}/manager-assessment` → writes `manager_rating` /
  `manager_notes`, requires status `Self Assessment Submitted`, moves to
  `Completed`.

Both accept `submit: false` to save a partial draft without advancing the
workflow; `submit: true` (the default) requires **everything** rated and is
rejected with a `400` listing exactly what's missing. A rejected submit rolls
back — a half-applied assessment would be worse than none. Completeness is
checked against what's stored, so drafts saved earlier count.

The manager sees the employee's ratings simply by reading the review: both sides
live on the same rows, and `GET /performance/reviews/{ref}` returns objectives
and competency ratings with `self_*` and `manager_*` side by side. The manager
assessment never modifies the employee's columns.

On each submit, three scores are computed once and **frozen** onto the review
(same reasoning as payslips snapshotting `gross_salary` — a later change can't
retroactively rewrite a submitted assessment):

- `*_objective_score` = `SUM(rating × weightage) / 100` — a weighted mean, back
  on the 1–5 scale because the weightages are guaranteed to total 100.
- `*_competency_score` = plain mean of the competency ratings (core competencies
  all count equally — there's no weighting concept there).
- `*_overall_rating` = `0.7 × objective + 0.3 × competency`. Those two weights
  are flat sample assumptions, same style as finance's `TAX_RATE` and
  `WORKING_DAYS_PER_MONTH`.

| Method | Path                                              | Purpose |
|--------|---------------------------------------------------|---------|
| GET    | `/performance/competencies`                       | The pre-defined core competencies — filter `active` |
| GET    | `/performance/reviews`                            | List/search — filters: `employee_id`, `manager_id`, `cycle_year`, `status`, `stage` |
| GET    | `/performance/reviews/{review_ref}`               | One review with its objectives + competency ratings (both sides) |
| POST   | `/performance/reviews`                            | Open a cycle for an employee/year (always starts `Draft`) |
| DELETE | `/performance/reviews/{review_ref}`               | Hard delete (test cleanup — cascades to objectives/ratings) |
| GET    | `/performance/reviews/{review_ref}/objectives`    | List a review's objectives |
| POST   | `/performance/reviews/{review_ref}/objectives`    | Add an objective (employee-editable statuses only) |
| PATCH  | `/performance/objectives/{objective_id}`          | Edit description/weightage (not ratings) |
| DELETE | `/performance/objectives/{objective_id}`          | Remove an objective |
| POST   | `/performance/reviews/{review_ref}/submit-objectives` | Employee: send objectives for approval (weightages must total 100) |
| POST   | `/performance/reviews/{review_ref}/review-objectives` | Manager: `Approve`, or `Send Back` with notes |
| POST   | `/performance/reviews/{review_ref}/self-assessment`   | Employee: rate objectives + competencies |
| POST   | `/performance/reviews/{review_ref}/manager-assessment`| Manager: rate the same, completing the review |

Other business rules enforced by the API:
- The reviewing `manager_id` is **snapshotted** from the employee's current
  manager when the cycle opens. A reorg mid-cycle does not move an in-flight
  review to the new manager.
- An employee with no manager (top of the org — `E-1000`/`E-1001`/`E-1002`)
  can't have a review: there'd be nobody to approve objectives (`400`).
  Terminated employees are rejected too (`400`); `On Leave` ones are fine.
- One review per employee per `cycle_year` (`409` on a duplicate).
- Ratings outside 1–5 → `422`; weightage outside 1–100 → `422`.
- Rating an objective that belongs to a different review, an unknown/retired
  competency, or the same thing twice in one payload → `400`.

Competencies are **read-only over the API** (`GET` only, no `POST`/`PATCH`/
`DELETE`) — a company-wide core competency list isn't something an employee or
manager edits per review. Change them in `scripts/build_performance.py`. The
`active` flag exists so one can be retired without breaking historical reviews
that already rated it: only active competencies are required on submit.

Seed data: 5 core competencies (`COLLAB`, `OWN`, `COMM`, `CUST`, `INNOV`) and 12
reviews covering **every** status in the workflow, so an agent can be pointed at
a review in any stage without having to drive one there first. `E-2043` has two
completed cycles (2025 and 2026) for year-on-year comparison; `PR-2026-E1902` is
sitting in `Objectives Sent Back` with the manager's notes; `PR-2026-E4890` is a
`Draft` whose weightages total 70 and `PR-2026-E2210` a `Draft` with no
objectives at all — the two cases `submit-objectives` rejects.

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

# Cross-domain example: explain a salary difference using leave data
erp.create_leave_request("E-2043", leave_type="Unpaid", status="Approved",
                          start_date="2026-07-06", end_date="2026-07-06",
                          reason="Personal matter")
payslip = erp.generate_payslip("E-2043", period_month=7, period_year=2026)
# payslip["unpaid_leave_days"] and payslip["leave_deduction"] explain why
# payslip["net_pay"] is lower than a period with no unpaid leave.
leave_history = erp.list_leave_requests(employee_id="E-2043", period_year=2026, period_month=7)

# Letters & certificates — request a "For Whom It May Concern" letter, get a PDF
req = erp.request_letter("E-2043", include_salary=True, include_bank_details=True,
                          addressed_to="The Consulate General of Canada",
                          purpose="a work visa application")
ref = req["request_ref"]                                       # "LC-000012", status "Pending"

erp.issue_letter_request(ref, notes="Checked against passport name.")
letter = erp.get_letter_content(ref)                           # fields + the exact paragraphs
letter["salary"]["gross_salary"]                               # frozen at issue, not live
erp.download_letter_document(ref, save_to="fwimc.pdf")         # the PDF the employee gets

# The plain variant (no salary, no bank) and the HR side of the workflow
plain = erp.request_letter("E-1187", purpose="a rental application")
erp.reject_letter_request(plain["request_ref"], "Please request this through your manager.")
queue = erp.list_letter_requests(status="Pending")             # HR's action queue
history = erp.list_letter_requests(employee_id="E-2043")       # newest first

# Performance management — a full cycle, both phases
review = erp.create_performance_review("E-2043", cycle_year=2027)
ref = review["review_ref"]                                     # "PR-2027-E2043"

# Objective setting: employee adds objectives, manager approves them
o1 = erp.add_objective(ref, "Ship v2 of the ingest pipeline", weightage=50)
o2 = erp.add_objective(ref, "Cut on-call pages from 40/mo to 20/mo", weightage=30)
o3 = erp.add_objective(ref, "Mentor one junior engineer", weightage=20)
erp.submit_objectives(ref)                                     # 400 unless they total 100
erp.send_back_objectives(ref, "Objective 2 needs a measurable target.")
erp.update_objective(o2["id"], description="Cut on-call pages from 40/mo to 20/mo")
erp.submit_objectives(ref)
erp.approve_objectives(ref, notes="Approved.")                 # -> stage "Appraisal"

# Appraisal: employee self-assesses, then the manager assesses the same items
competencies = erp.list_competencies(active=True)
erp.submit_self_assessment(
    ref,
    objectives=[{"objective_id": o1["id"], "rating": 5, "notes": "Shipped in March."},
                {"objective_id": o2["id"], "rating": 4, "notes": "Down to 22/mo."},
                {"objective_id": o3["id"], "rating": 3}],
    competencies=[{"competency_code": c["code"], "rating": 4} for c in competencies],
)
done = erp.submit_manager_assessment(
    ref,
    objectives=[{"objective_id": o1["id"], "rating": 4, "notes": "Shipped, scope trimmed."},
                {"objective_id": o2["id"], "rating": 5},
                {"objective_id": o3["id"], "rating": 3}],
    competencies=[{"competency_code": c["code"], "rating": 4} for c in competencies],
)
# done["status"] == "Completed"; self_overall_rating vs manager_overall_rating
# quantify the gap, and done["objectives"] carries both sides' ratings + notes.

# A manager's action queue, and one employee's history across cycles
queue = erp.list_performance_reviews(manager_id="E-3320", status="Objectives Submitted")
history = erp.list_performance_reviews(employee_id="E-2043")   # newest cycle first
```

To point at a different environment (real ERP, staging, etc.):

```bash
export ERP_BASE_URL=https://real-erp.company.com/api
```

or `ERPClient(base_url="https://real-erp.company.com/api")` explicitly.

## Adding the next module (e.g. expense reports)

1. Add `db/schema_expenses.sql` + a `scripts/build_expenses.py` seeder (call it after `build_employees.py`, same pattern as `build_finance.py`).
2. Add `app/schemas/expenses.py` (Pydantic models).
3. Add `app/routers/expenses.py` (endpoints), same CRUD pattern as `employees.py`/`finance.py` — or, if the module has an approval workflow, the state-machine pattern in `performance.py` (status guards + action endpoints, never a caller-settable status); `letters.py` is the short version of the same thing.
4. Register it in `app/main.py`: `app.include_router(expenses.router)`.
5. Add corresponding methods to `erp_client.py` under a `# ---- Expenses module ----` section.
6. Add the new seed script to `entrypoint.sh`'s seeding block.

Keeping every module's router + schema + client methods this consistent is
what makes the eventual "swap to the real ERP" a config change instead of a rewrite.
