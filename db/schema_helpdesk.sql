-- ============================================================
-- ERP Sample App — Helpdesk Module Schema
-- Tickets filed by employees, assigned to employees, tracked through a
-- status workflow (Open -> In Progress -> Resolved -> Closed).
-- ============================================================

CREATE TABLE IF NOT EXISTS tickets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id     TEXT    NOT NULL UNIQUE,     -- server-generated, e.g. TCK-000042 (derived from id post-insert)
    subject       TEXT    NOT NULL,
    description   TEXT    NOT NULL,
    requester_id  TEXT    NOT NULL,            -- FK -> employees.employee_id, immutable after creation
    assignee_id   TEXT,                        -- FK -> employees.employee_id, nullable (unassigned)
    category      TEXT    NOT NULL DEFAULT 'General',  -- IT, HR, Finance, Facilities, General (open-ended)
    priority      TEXT    NOT NULL DEFAULT 'Medium',   -- Low, Medium, High, Urgent
    status        TEXT    NOT NULL DEFAULT 'Open',     -- Open, In Progress, Resolved, Closed
    resolved_at   TEXT,                        -- set when status enters Resolved/Closed; NOT cleared on reopen
    closed_at     TEXT,                        -- set when status enters Closed; NOT cleared on reopen
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (requester_id) REFERENCES employees(employee_id),
    FOREIGN KEY (assignee_id) REFERENCES employees(employee_id)
);

CREATE INDEX IF NOT EXISTS idx_tickets_requester ON tickets(requester_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assignee ON tickets(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
