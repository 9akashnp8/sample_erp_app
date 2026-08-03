"""
Builds/seeds the performance management module tables: competencies,
performance_reviews, performance_objectives, performance_competency_ratings.
Assumes employees table already exists (run build_employees.py first).
Re-run any time to reset the performance tables to seed state.

The seed deliberately covers every status in the workflow so an agent can be
pointed at a review in any stage without having to drive one there first.
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "erp.db")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", os.path.join(BASE_DIR, "db"))
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "schema_performance.sql")

# Duplicated from app/routers/performance.py rather than imported — seed
# scripts here stay standalone (build_finance.py duplicates _fake_encrypt the
# same way) so they can run without the app package importable.
OBJECTIVES_WEIGHT = 0.7
COMPETENCIES_WEIGHT = 0.3
TOTAL_WEIGHTAGE = 100

# (code, name, description)
COMPETENCIES = [
    ("COLLAB", "Collaboration",
     "Works effectively across teams, shares context early, and helps others succeed."),
    ("OWN", "Ownership & Accountability",
     "Takes end-to-end responsibility for outcomes and follows through without being chased."),
    ("COMM", "Communication",
     "Writes and speaks clearly, tailors the message to the audience, and listens actively."),
    ("CUST", "Customer Focus",
     "Starts from the customer's problem and measures success by their outcome."),
    ("INNOV", "Innovation & Continuous Improvement",
     "Challenges how the team works, not just what it ships, and acts on what they find."),
]

# Which timestamp columns are populated at each status — a review that has
# reached a status has necessarily passed through the earlier ones.
STATUS_TIMESTAMPS = {
    "Draft": (),
    "Objectives Submitted": ("objectives_submitted_at",),
    "Objectives Sent Back": ("objectives_submitted_at",),
    "Objectives Approved": ("objectives_submitted_at", "objectives_approved_at"),
    "Self Assessment Submitted": ("objectives_submitted_at", "objectives_approved_at",
                                  "self_assessment_submitted_at"),
    "Completed": ("objectives_submitted_at", "objectives_approved_at",
                  "self_assessment_submitted_at", "completed_at"),
}

# Statuses at which each side's ratings exist. Seed rows below always carry
# both sides' ratings; whichever side hasn't happened yet is nulled out on
# insert, so the data can't describe a review that has manager ratings before
# the employee has self-assessed.
SELF_RATED_STATUSES = ("Self Assessment Submitted", "Completed")
MANAGER_RATED_STATUSES = ("Completed",)


def _timeline(year: int) -> dict:
    """A plausible annual cycle: objectives set in January, appraisal in July."""
    return {
        "objectives_submitted_at": f"{year}-01-12 09:14:00",
        "objectives_approved_at": f"{year}-01-16 10:02:00",
        "self_assessment_submitted_at": f"{year}-07-20 11:35:00",
        "completed_at": f"{year}-07-28 14:20:00",
    }


# Competency ratings per review, as
# code -> (self_rating, self_notes, manager_rating, manager_notes).
# Manager entries are None on reviews that haven't reached the manager yet.
PRIYA_2026_COMPETENCIES = {
    "COLLAB": (5, "Ran the cross-team migration syncs and unblocked Design twice.", 5, "Genuinely raised the bar for how the team coordinates."),
    "OWN": (5, "Owned the payments cutover end to end, including the rollback plan.", 4, "Strong ownership; would like to see it extended to on-call follow-ups."),
    "COMM": (4, "Design docs landed well; still working on being concise in reviews.", 4, "Agreed — the writing is excellent, review comments can be shorter."),
    "CUST": (4, "Shadowed three support calls before scoping the retry work.", 5, "Best customer instincts on the team this cycle."),
    "INNOV": (4, "Introduced the perf budget check in CI.", 4, "The CI budget check has already caught two regressions."),
}

PRIYA_2025_COMPETENCIES = {
    "COLLAB": (4, "Paired regularly with the two new joiners.", 4, "Reliable partner across the team."),
    "OWN": (4, "Carried the search rewrite to completion.", 4, "Delivered as promised."),
    "COMM": (3, "Needed a few passes to get the RFC readable.", 3, "Improving; keep writing."),
    "CUST": (4, "Pulled ticket themes into the roadmap discussion.", 4, "Good use of support data."),
    "INNOV": (3, "Mostly executed the existing plan this year.", 4, "Better than self-assessed — the caching idea was hers."),
}

JAMES_COMPETENCIES = {
    "COLLAB": (4, "Reviewed most of the team's PRs within a day.", None, None),
    "OWN": (4, "Picked up the flaky-test cleanup nobody wanted.", None, None),
    "COMM": (3, "Async updates are inconsistent — working on it.", None, None),
    "CUST": (3, "Limited direct customer contact this cycle.", None, None),
    "INNOV": (4, "Prototyped the new job runner in a hack week.", None, None),
}

DEREK_COMPETENCIES = {
    "COLLAB": (5, "Embedded with Sales and Engineering for the whole hiring push.", None, None),
    "OWN": (4, "Owned the policy refresh end to end.", None, None),
    "COMM": (5, "Ran every all-hands HR segment this year.", None, None),
    "CUST": (4, "Treated managers as the customer for the new handbook.", None, None),
    "INNOV": (3, "Kept mostly to established process this cycle.", None, None),
}

TOM_COMPETENCIES = {
    "COLLAB": (3, "Could loop in Solutions earlier on complex deals.", 3, "Agreed — earlier engagement would have saved two deals."),
    "OWN": (4, "Ran my own pipeline hygiene without prompting.", 4, "Forecast accuracy was the best on the team."),
    "COMM": (4, "Clear, well-structured customer proposals.", 5, "Proposals are being reused as templates by the rest of Sales."),
    "CUST": (5, "Held quarterly check-ins with every named account.", 4, "Strong, though a couple of smaller accounts went quiet."),
    "INNOV": (3, "Trialled the new demo script.", 3, "Fine — not a focus area this cycle."),
}

# Each review: employee_id, cycle_year, status, objectives (description,
# weightage, self_rating, self_notes, manager_rating, manager_notes),
# competency ratings, and the manager's objective-review notes.
REVIEWS = [
    {
        # Two cycles for E-2043 (the README's running example) so year-on-year
        # comparison has something to compare.
        "employee_id": "E-2043", "cycle_year": 2025, "status": "Completed",
        "objectives_manager_notes": "Objectives approved as written.",
        "objectives": [
            ("Ship the search rewrite to general availability", 50, 4, "Shipped in May, two weeks late.", 4, "Late but solid; the slip was upstream."),
            ("Reduce p95 API latency by 20%", 30, 3, "Landed at 14% — short of target.", 3, "Real progress, target missed."),
            ("Mentor two new engineers through onboarding", 20, 5, "Both ramped inside a month.", 5, "Both are productive; excellent."),
        ],
        "competencies": PRIYA_2025_COMPETENCIES,
    },
    {
        "employee_id": "E-2043", "cycle_year": 2026, "status": "Completed",
        "objectives_manager_notes": "Good set — sharpened the reliability target before approving.",
        "objectives": [
            ("Lead the payments platform migration to completion", 40, 5, "Cut over with zero customer-visible downtime.", 5, "Flawless execution on the highest-risk project of the year."),
            ("Hold API error rate under 0.1% across the year", 35, 4, "Two breaches, both recovered inside an hour.", 4, "Met the spirit of the target."),
            ("Publish and adopt the team's engineering standards doc", 25, 4, "Written and adopted; enforcement is still manual.", 3, "Adopted, but the manual enforcement was in scope."),
        ],
        "competencies": PRIYA_2026_COMPETENCIES,
    },
    {
        "employee_id": "E-1187", "cycle_year": 2026, "status": "Self Assessment Submitted",
        "objectives_manager_notes": "Approved — realistic scope for the first full year.",
        "objectives": [
            ("Take ownership of the notifications service", 40, 4, "On-call and roadmap for it are mine now.", None, None),
            ("Cut the flaky test rate below 1%", 35, 5, "Down from 6% to 0.4%.", None, None),
            ("Complete the internal distributed systems course", 25, 3, "Four of six modules done.", None, None),
        ],
        "competencies": JAMES_COMPETENCIES,
    },
    {
        "employee_id": "E-3320", "cycle_year": 2026, "status": "Objectives Approved",
        "objectives_manager_notes": "Approved. Let's revisit the hiring target at the half-year point.",
        "objectives": [
            ("Grow the platform team from 4 to 7 engineers", 40, None, None, None, None),
            ("Bring average PR review turnaround under 8 hours", 30, None, None, None, None),
            ("Run quarterly career conversations with every report", 30, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        "employee_id": "E-2891", "cycle_year": 2026, "status": "Objectives Approved",
        "objectives_manager_notes": "Approved as submitted.",
        "objectives": [
            ("Book 120 qualified meetings", 50, None, None, None, None),
            ("Maintain a 25% meeting-to-opportunity conversion rate", 30, None, None, None, None),
            ("Build a reusable outbound sequence library", 20, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        "employee_id": "E-3110", "cycle_year": 2026, "status": "Self Assessment Submitted",
        "objectives_manager_notes": "Approved.",
        "objectives": [
            ("Roll out the refreshed performance review process company-wide", 40, 4, "Rolled out on schedule; adoption is at 80%.", None, None),
            ("Cut average time-to-hire to 30 days", 35, 3, "Sitting at 38 days — improved but short.", None, None),
            ("Run manager training for every people manager", 25, 5, "All 6 managers completed both sessions.", None, None),
        ],
        "competencies": DEREK_COMPETENCIES,
    },
    {
        "employee_id": "E-2765", "cycle_year": 2026, "status": "Completed",
        "objectives_manager_notes": "Approved after trimming the fourth objective — three is enough.",
        "objectives": [
            ("Close $1.2M in new business", 50, 4, "Closed $1.05M — missed on one slipped deal.", 3, "Miss is a miss; the slipped deal was foreseeable in Q2."),
            ("Grow the enterprise pipeline to 3x quota", 30, 4, "Pipeline finished at 3.2x.", 4, "Genuinely strong pipeline discipline."),
            ("Hand over the SMB book cleanly", 20, 5, "Fully handed over with notes by March.", 5, "Cleanest handover we've had."),
        ],
        "competencies": TOM_COMPETENCIES,
    },
    {
        "employee_id": "E-4501", "cycle_year": 2026, "status": "Objectives Submitted",
        "objectives_manager_notes": None,
        "objectives": [
            ("Automate the regression suite for the checkout flow", 45, None, None, None, None),
            ("Keep escaped-defect count under 5 for the year", 35, None, None, None, None),
            ("Document the release verification checklist", 20, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        "employee_id": "E-3502", "cycle_year": 2026, "status": "Objectives Submitted",
        "objectives_manager_notes": None,
        "objectives": [
            ("Fill all 7 open engineering roles", 60, None, None, None, None),
            ("Build a candidate pipeline for the Berlin office", 40, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        # Sent back with notes — the state an employee revises objectives from.
        "employee_id": "E-1902", "cycle_year": 2026, "status": "Objectives Sent Back",
        "objectives_manager_notes": ("Objectives 1 and 2 aren't measurable — give me a number or a date for each. "
                                     "Also 60% on the design system feels high relative to the product work."),
        "objectives": [
            ("Improve the design system", 60, None, None, None, None),
            ("Support the mobile redesign", 25, None, None, None, None),
            ("Run monthly design critiques", 15, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        # Draft with an incomplete weightage total (70) — submitting this
        # review as-is is exactly the 400 that submit-objectives raises.
        "employee_id": "E-4890", "cycle_year": 2026, "status": "Draft",
        "objectives_manager_notes": None,
        "objectives": [
            ("Complete the intern project and demo it to the team", 40, None, None, None, None),
            ("Land 10 reviewed pull requests", 30, None, None, None, None),
        ],
        "competencies": {},
    },
    {
        # Draft with no objectives yet — the other submit-objectives 400.
        "employee_id": "E-2210", "cycle_year": 2026, "status": "Draft",
        "objectives_manager_notes": None,
        "objectives": [],
        "competencies": {},
    },
]


def _scores(objectives: list, competency_ratings: list) -> tuple:
    """Same math as _compute_scores in app/routers/performance.py.
    `objectives` is a list of (weightage, rating); `competency_ratings` a
    flat list of ratings. Callers pass one side (self or manager) at a time."""
    objective_score = round(
        sum(rating * weightage for weightage, rating in objectives) / TOTAL_WEIGHTAGE, 2
    ) if objectives else None
    competency_score = round(
        sum(competency_ratings) / len(competency_ratings), 2
    ) if competency_ratings else None
    if objective_score is not None and competency_score is not None:
        overall = round(OBJECTIVES_WEIGHT * objective_score + COMPETENCIES_WEIGHT * competency_score, 2)
    else:
        overall = objective_score if objective_score is not None else competency_score
    return objective_score, competency_score, overall


def build():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Children first — performance_objectives / performance_competency_ratings
    # reference performance_reviews, which references competencies.
    cur.execute("DROP TABLE IF EXISTS performance_competency_ratings")
    cur.execute("DROP TABLE IF EXISTS performance_objectives")
    cur.execute("DROP TABLE IF EXISTS performance_reviews")
    cur.execute("DROP TABLE IF EXISTS competencies")
    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())

    # Sanity check: employees table must already exist and be populated
    try:
        emp_count = cur.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    except sqlite3.OperationalError:
        raise RuntimeError(
            "employees table not found. Run scripts/build_employees.py first."
        )
    if emp_count == 0:
        raise RuntimeError("employees table is empty. Run scripts/build_employees.py first.")

    cur.executemany(
        "INSERT INTO competencies (code, name, description) VALUES (?,?,?)",
        COMPETENCIES,
    )
    competency_ids = {
        code: cur.execute("SELECT id FROM competencies WHERE code = ?", (code,)).fetchone()[0]
        for code, _, _ in COMPETENCIES
    }

    objective_count = 0
    for review in REVIEWS:
        employee_id, year, status = review["employee_id"], review["cycle_year"], review["status"]
        manager_id = cur.execute(
            "SELECT manager_id FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if manager_id is None or manager_id[0] is None:
            raise RuntimeError(
                f"Seed error: {employee_id} has no manager, so it cannot have a performance review."
            )
        manager_id = manager_id[0]

        timeline = _timeline(year)
        stamps = {col: timeline[col] for col in STATUS_TIMESTAMPS[status]}
        has_self = status in SELF_RATED_STATUSES
        has_manager = status in MANAGER_RATED_STATUSES

        # Ratings are nulled out for whichever side hasn't happened yet, so the
        # seed can carry the full story per objective without describing an
        # impossible state.
        objectives = [
            (desc, weight,
             self_rating if has_self else None, self_notes if has_self else None,
             mgr_rating if has_manager else None, mgr_notes if has_manager else None)
            for desc, weight, self_rating, self_notes, mgr_rating, mgr_notes in review["objectives"]
        ]
        competencies = {
            code: (self_rating if has_self else None, self_notes if has_self else None,
                   mgr_rating if has_manager else None, mgr_notes if has_manager else None)
            for code, (self_rating, self_notes, mgr_rating, mgr_notes) in review["competencies"].items()
        } if (has_self or has_manager) else {}

        self_scores = _scores(
            [(w, r) for _, w, r, _, _, _ in objectives if r is not None],
            [v[0] for v in competencies.values() if v[0] is not None],
        ) if has_self else (None, None, None)
        manager_scores = _scores(
            [(w, r) for _, w, _, _, r, _ in objectives if r is not None],
            [v[2] for v in competencies.values() if v[2] is not None],
        ) if has_manager else (None, None, None)

        ref = f"PR-{year}-{employee_id.replace('E-', 'E')}"
        cur.execute(
            """
            INSERT INTO performance_reviews
            (review_ref, employee_id, manager_id, cycle_year, status, objectives_manager_notes,
             self_objective_score, self_competency_score, self_overall_rating,
             manager_objective_score, manager_competency_score, manager_overall_rating,
             objectives_submitted_at, objectives_approved_at,
             self_assessment_submitted_at, completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (ref, employee_id, manager_id, year, status, review["objectives_manager_notes"],
             *self_scores, *manager_scores,
             stamps.get("objectives_submitted_at"), stamps.get("objectives_approved_at"),
             stamps.get("self_assessment_submitted_at"), stamps.get("completed_at")),
        )
        review_id = cur.lastrowid

        for desc, weight, self_rating, self_notes, mgr_rating, mgr_notes in objectives:
            cur.execute(
                """
                INSERT INTO performance_objectives
                (review_id, description, weightage, self_rating, self_notes, manager_rating, manager_notes)
                VALUES (?,?,?,?,?,?,?)
                """,
                (review_id, desc, weight, self_rating, self_notes, mgr_rating, mgr_notes),
            )
            objective_count += 1

        for code, (self_rating, self_notes, mgr_rating, mgr_notes) in competencies.items():
            cur.execute(
                """
                INSERT INTO performance_competency_ratings
                (review_id, competency_id, self_rating, self_notes, manager_rating, manager_notes)
                VALUES (?,?,?,?,?,?)
                """,
                (review_id, competency_ids[code], self_rating, self_notes, mgr_rating, mgr_notes),
            )

    conn.commit()
    conn.close()
    print(f"Seeded {len(COMPETENCIES)} competencies, {len(REVIEWS)} performance reviews "
          f"and {objective_count} objectives.")


if __name__ == "__main__":
    build()
