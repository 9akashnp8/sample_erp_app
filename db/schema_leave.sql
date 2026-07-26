-- ============================================================
-- ERP Sample App — Leave Module Schema
-- Leave requests are created already in their final state
-- (Approved/Rejected/Cancelled) — there is no approver role or
-- workflow modeled in this app; the caller states the outcome
-- directly, same spirit as this app having no separate auth system.
-- ============================================================

CREATE TABLE IF NOT EXISTS leave_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_id      TEXT    NOT NULL UNIQUE,   -- server-generated, e.g. LV-000012 (derived from id post-insert)
    employee_id   TEXT    NOT NULL,           -- FK -> employees.employee_id, immutable after creation
    leave_type    TEXT    NOT NULL,           -- Annual, Sick, Unpaid, Other
    status        TEXT    NOT NULL,           -- Approved, Rejected, Cancelled — no default; caller states it directly
    start_date    TEXT    NOT NULL,
    end_date      TEXT    NOT NULL,
    days          INTEGER NOT NULL,           -- server-computed: (end_date - start_date).days + 1, calendar days
                                               -- (no weekend/holiday modeling — a range spanning a weekend
                                               -- overstates days relative to actual working days lost)
    reason        TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- No overlap/uniqueness constraint on (employee_id, start_date, end_date):
-- range overlap isn't expressible as a SQLite UNIQUE and this app has no
-- precedent for that validation. Overlapping Approved+Unpaid requests for
-- the same employee will double-count in the payslip deduction (SUM(days))
-- — seed data must stay non-overlapping by construction.
--
-- leave_requests.status is intentionally NOT synced with the existing
-- employees.status = 'On Leave' value — no automation between them.

CREATE INDEX IF NOT EXISTS idx_leave_requests_employee ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_start_date ON leave_requests(start_date);
