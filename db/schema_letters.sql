-- ============================================================
-- ERP Sample App — Letters & Certificates Module Schema
-- Employee self-service requests for official letters. Only one
-- letter_type is modeled so far: "For Whom It May Concern".
--
-- Unlike Leave (created already in its final state), a letter request
-- follows a small approval workflow — Pending -> Issued/Rejected, or
-- Cancelled by the requester — because the issued document carries the
-- organization's name and someone in HR signs off before it exists.
-- Same status-guard pattern as performance_reviews, one step shorter.
-- ============================================================

CREATE TABLE IF NOT EXISTS letter_requests (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    request_ref           TEXT    NOT NULL UNIQUE,  -- server-generated, e.g. LC-000012 (derived from id post-insert)
    employee_id           TEXT    NOT NULL,          -- FK -> employees.employee_id, immutable after creation
    letter_type           TEXT    NOT NULL DEFAULT 'For Whom It May Concern',
                                                     -- single value today; the column (rather than a hardcoded
                                                     -- template) is the extension point for Experience Letter,
                                                     -- NOC, etc. — add the value + a body template, no migration.
    include_salary        INTEGER NOT NULL DEFAULT 0,  -- 0/1 — adds the salary paragraph
    include_bank_details  INTEGER NOT NULL DEFAULT 0,  -- 0/1 — adds the bank paragraph
    addressed_to          TEXT,                       -- e.g. "The Consulate General of Canada"; NULL renders as "To Whom It May Concern"
    purpose               TEXT,                       -- e.g. "visa application" — appears in the closing paragraph
    status                TEXT    NOT NULL DEFAULT 'Pending',  -- Pending, Issued, Rejected, Cancelled — never caller-settable
    decision_notes        TEXT,                       -- rejection reason (required to reject) or an optional note on issue
    document_ref          TEXT    UNIQUE,             -- assigned at issue, e.g. FWIMC-2026-E2043-000012; NULL until then
    issued_at             TEXT,                       -- NULL until issued

    -- Details snapshotted at issue time, not read live at download time.
    -- Same reasoning as payslips.gross_salary: a letter is a document that
    -- was true on the day it was issued, so re-downloading it after a raise
    -- or a job title change must not silently reprint different figures.
    -- All NULL while the request is Pending; the salary_* / bank_* groups
    -- stay NULL unless the corresponding include_* flag was set.
    snapshot_full_name              TEXT,
    snapshot_job_title              TEXT,
    snapshot_department             TEXT,
    snapshot_employment_type        TEXT,
    snapshot_hire_date              TEXT,
    snapshot_gross_salary           REAL,
    snapshot_currency               TEXT,
    snapshot_pay_frequency          TEXT,
    snapshot_bank_name              TEXT,
    snapshot_account_holder_name    TEXT,
    snapshot_masked_account_number  TEXT,   -- masked, never the full number — see note below
    snapshot_iban                   TEXT,
    snapshot_swift_bic              TEXT,

    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now')),

    -- Bank details only make sense alongside the salary paragraph (they are
    -- there to say where that salary is credited), and the real ERP's form
    -- gates the bank checkbox behind the salary one. Enforced here as well as
    -- in the API so the seed script can't create a combination the API refuses.
    CHECK (include_bank_details = 0 OR include_salary = 1),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- A real letter shows the full account number; this app never exposes one
-- (bank_accounts.encrypted_account_number is write-only by design, see
-- schema_finance.sql), so the issued letter prints the masked form. That is a
-- deliberate mock-only difference — the field to swap when the real ERP is wired up.

CREATE INDEX IF NOT EXISTS idx_letter_requests_employee ON letter_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_letter_requests_status ON letter_requests(status);
