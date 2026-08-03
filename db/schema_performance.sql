-- ============================================================
-- ERP Sample App — Performance Management Module Schema
--
-- Unlike the Leave module (no approval workflow — the caller states the
-- final outcome directly), performance management IS a workflow: a review
-- moves through a fixed sequence of statuses, and the API refuses
-- out-of-order transitions. That's the whole point of the module, so the
-- state machine lives in the API rather than being caller-suppliable.
--
--   Objective Setting stage        Appraisal stage           Done
--   ----------------------------   -----------------------   ---------
--   Draft                          Objectives Approved       Completed
--     -> Objectives Submitted        -> Self Assessment Submitted
--     -> Objectives Sent Back          -> Completed
--     (Sent Back -> Submitted again)
--
-- `stage` is NOT stored — it's derived from `status` in the router, so the
-- two can never drift out of sync.
-- ============================================================

-- Pre-defined company core competencies. Reference/seed data: the API
-- exposes GET only (no POST/PATCH/DELETE) because "company core
-- competencies" are a fixed company-wide list in this sample, not something
-- an employee or manager edits per review. `active` exists so a competency
-- can be retired without breaking historical reviews that already rated it.
CREATE TABLE IF NOT EXISTS competencies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,   -- stable business key used in API payloads, e.g. COLLAB
    name        TEXT    NOT NULL,
    description TEXT,
    active      INTEGER NOT NULL DEFAULT 1, -- 0/1 boolean; only active ones are required on submit
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- One review per employee per cycle year — the container both phases hang off.
CREATE TABLE IF NOT EXISTS performance_reviews (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    review_ref    TEXT    NOT NULL UNIQUE,  -- server-generated, e.g. PR-2026-E2043 (same shape as payslip_ref)
    employee_id   TEXT    NOT NULL,          -- FK -> employees.employee_id, immutable after creation
    manager_id    TEXT    NOT NULL,          -- FK -> employees.employee_id; SNAPSHOT of employees.manager_id
                                             -- taken at creation. A reorg mid-cycle does NOT move an
                                             -- in-flight review to the new manager — the reviewer stays
                                             -- whoever it was when the cycle opened (same spirit as
                                             -- payslips snapshotting gross_salary).
    cycle_year    INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'Draft',  -- see state machine above; never caller-suppliable
    objectives_manager_notes TEXT,           -- notes from the manager's objective review (send-back reason
                                             -- or approval comment). Only the latest is kept — no
                                             -- comment thread/history table, same minimalism as the rest
                                             -- of this app.

    -- Scores are computed and frozen at submit time, not on read, so a later
    -- edit to a competency list or weightage can't retroactively change a
    -- submitted assessment (same reason payslips snapshot gross_salary).
    self_objective_score      REAL,          -- SUM(self_rating * weightage) / 100
    self_competency_score     REAL,          -- AVG(self_rating) over active competencies
    self_overall_rating       REAL,          -- OBJECTIVES_WEIGHT * obj + COMPETENCIES_WEIGHT * comp
    manager_objective_score   REAL,
    manager_competency_score  REAL,
    manager_overall_rating    REAL,

    objectives_submitted_at      TEXT,
    objectives_approved_at       TEXT,
    self_assessment_submitted_at TEXT,
    completed_at                 TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id),
    UNIQUE (employee_id, cycle_year)         -- one review per employee per year
);

CREATE INDEX IF NOT EXISTS idx_performance_reviews_employee ON performance_reviews(employee_id);
CREATE INDEX IF NOT EXISTS idx_performance_reviews_manager ON performance_reviews(manager_id);
CREATE INDEX IF NOT EXISTS idx_performance_reviews_status ON performance_reviews(status);

-- Objectives belong to a review, not directly to an employee — an objective
-- has no meaning outside the cycle it was set for. Keyed on the internal
-- review id (not review_ref) since this is a pure child table.
CREATE TABLE IF NOT EXISTS performance_objectives (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id      INTEGER NOT NULL,
    description    TEXT    NOT NULL,
    weightage      INTEGER NOT NULL,        -- 1-100; the review's objectives must total exactly 100 to submit
    self_rating    INTEGER,                 -- 1-5, NULL until the employee self-assesses
    self_notes     TEXT,
    manager_rating INTEGER,                 -- 1-5, NULL until the manager assesses
    manager_notes  TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (review_id) REFERENCES performance_reviews(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_performance_objectives_review ON performance_objectives(review_id);

-- One row per (review, competency) pair, created lazily on first assessment
-- save rather than pre-populated when a review opens — that way retiring or
-- adding a competency mid-cycle doesn't leave orphan rows to clean up.
CREATE TABLE IF NOT EXISTS performance_competency_ratings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id      INTEGER NOT NULL,
    competency_id  INTEGER NOT NULL,
    self_rating    INTEGER,                 -- 1-5
    self_notes     TEXT,
    manager_rating INTEGER,                 -- 1-5
    manager_notes  TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (review_id) REFERENCES performance_reviews(id) ON DELETE CASCADE,
    FOREIGN KEY (competency_id) REFERENCES competencies(id),
    UNIQUE (review_id, competency_id)
);

CREATE INDEX IF NOT EXISTS idx_performance_competency_ratings_review ON performance_competency_ratings(review_id);

-- The two ON DELETE CASCADE clauses above are what make
-- DELETE /performance/reviews/{review_ref} a single statement. They only fire
-- because app/database.py sets `PRAGMA foreign_keys = ON` per connection —
-- SQLite ignores FK actions otherwise. Seed scripts connect without that
-- pragma, but they DROP the child tables outright, so it doesn't matter there.
