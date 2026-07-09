-- ============================================================
-- ERP Sample App — Employee Module Schema
-- ============================================================

CREATE TABLE IF NOT EXISTS employees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     TEXT    NOT NULL UNIQUE,     -- business-facing id, e.g. E-2043
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    job_title       TEXT    NOT NULL,
    department      TEXT    NOT NULL,
    manager_id      TEXT,                        -- FK -> employees.employee_id (nullable, top of org has NULL)
    employment_type TEXT    NOT NULL DEFAULT 'Full-Time',  -- Full-Time, Part-Time, Contractor, Intern
    status          TEXT    NOT NULL DEFAULT 'Active',      -- Active, On Leave, Terminated
    hire_date       TEXT    NOT NULL,
    termination_date TEXT,
    location        TEXT,                        -- office / city
    phone           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);

CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);
