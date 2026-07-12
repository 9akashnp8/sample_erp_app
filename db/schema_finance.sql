-- ============================================================
-- ERP Sample App — Finance Module Schema
-- Bank accounts, salary info, payslips
-- ============================================================

CREATE TABLE IF NOT EXISTS bank_accounts (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id               TEXT    NOT NULL,          -- FK -> employees.employee_id
    bank_name                 TEXT    NOT NULL,
    account_holder_name       TEXT    NOT NULL,
    masked_account_number     TEXT    NOT NULL,          -- e.g. "****4821" — safe to display/log
    encrypted_account_number  TEXT    NOT NULL,          -- placeholder for a real encrypted value; NEVER return via API
    iban                      TEXT,
    swift_bic                 TEXT,
    currency                  TEXT    NOT NULL DEFAULT 'USD',
    is_primary                INTEGER NOT NULL DEFAULT 1, -- 0/1 boolean; one primary account per employee
    status                    TEXT    NOT NULL DEFAULT 'Active',  -- Active, Inactive
    created_at                TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_employee ON bank_accounts(employee_id);

-- One active salary record per employee. Kept simple (single gross figure)
-- but effective_date is included so a future version can support salary
-- history without a schema change — just stop treating "latest" as "only".
CREATE TABLE IF NOT EXISTS salary_info (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id       TEXT    NOT NULL UNIQUE,          -- FK -> employees.employee_id (one active row per employee)
    gross_salary      REAL    NOT NULL,                 -- monthly gross, in `currency`
    currency           TEXT    NOT NULL DEFAULT 'USD',
    pay_frequency     TEXT    NOT NULL DEFAULT 'Monthly', -- Monthly (only supported value for now)
    effective_date    TEXT    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS payslips (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    payslip_ref         TEXT    NOT NULL UNIQUE,        -- e.g. PS-2026-06-E2043
    employee_id         TEXT    NOT NULL,                -- FK -> employees.employee_id
    period_month        INTEGER NOT NULL,                 -- 1-12
    period_year         INTEGER NOT NULL,
    gross_salary        REAL    NOT NULL,                 -- snapshot at generation time
    tax_deduction       REAL    NOT NULL DEFAULT 0,
    other_deductions    REAL    NOT NULL DEFAULT 0,
    other_deductions_note TEXT,
    net_pay             REAL    NOT NULL,                 -- gross - tax - other
    currency            TEXT    NOT NULL DEFAULT 'USD',
    status              TEXT    NOT NULL DEFAULT 'Generated', -- Generated, Sent
    generated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    UNIQUE (employee_id, period_month, period_year)      -- one payslip per employee per period
);

CREATE INDEX IF NOT EXISTS idx_payslips_employee ON payslips(employee_id);
CREATE INDEX IF NOT EXISTS idx_payslips_period ON payslips(period_year, period_month);
