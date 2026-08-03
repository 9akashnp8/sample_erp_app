import sqlite3
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.schemas.performance import (
    Competency, Objective, CompetencyRating,
    PerformanceReview, PerformanceReviewDetail, PerformanceReviewCreate,
    ObjectiveCreate, ObjectiveUpdate,
    ObjectiveReviewRequest, AssessmentRequest,
)

router = APIRouter(prefix="/performance", tags=["Performance"])

# Flat sample weights for rolling objective + competency scores into one
# number, same style as finance.py's TAX_RATE / WORKING_DAYS_PER_MONTH.
OBJECTIVES_WEIGHT = 0.7
COMPETENCIES_WEIGHT = 0.3

TOTAL_WEIGHTAGE = 100  # a review's objectives must total exactly this to be submitted

# The state machine from db/schema_performance.sql, expressed as data so the
# transition guards below stay one-liners.
STAGE_BY_STATUS = {
    "Draft": "Objective Setting",
    "Objectives Submitted": "Objective Setting",
    "Objectives Sent Back": "Objective Setting",
    "Objectives Approved": "Appraisal",
    "Self Assessment Submitted": "Appraisal",
    "Completed": "Completed",
}

# Statuses in which an objective's definition (description/weightage) may
# still be added, edited or removed — i.e. before the manager has it.
OBJECTIVE_EDITABLE_STATUSES = ("Draft", "Objectives Sent Back")

# Per-role config for the two assessment endpoints, which are otherwise
# identical: same payload, same validation, same scoring — only the columns
# written and the status transition differ.
ASSESSMENT_ROLES = {
    "self": {
        "required_status": "Objectives Approved",
        "submitted_status": "Self Assessment Submitted",
        "timestamp_column": "self_assessment_submitted_at",
    },
    "manager": {
        "required_status": "Self Assessment Submitted",
        "submitted_status": "Completed",
        "timestamp_column": "completed_at",
    },
}


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _now() -> str:
    """Matches the `datetime('now')` string shape used elsewhere in this app."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _require_employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    emp = conn.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
    return emp


def _require_review(conn: sqlite3.Connection, review_ref: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM performance_reviews WHERE review_ref = ?", (review_ref,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Performance review '{review_ref}' not found")
    return row


def _require_status(review: sqlite3.Row, *allowed: str) -> None:
    """409 on an out-of-order workflow transition. 409 (not 400) because the
    request is well-formed — it's the review's current state that conflicts,
    same reasoning as finance.py's duplicate-payslip 409."""
    if review["status"] not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(f"Review '{review['review_ref']}' is in status '{review['status']}'; "
                    f"this action requires status {' or '.join(repr(s) for s in allowed)}."),
        )


def _review_response(review: sqlite3.Row) -> dict:
    """Adds the derived `stage`. Never stored — see schema comments."""
    return dict(review, stage=STAGE_BY_STATUS[review["status"]])


def _fetch_objectives(conn: sqlite3.Connection, review_id: int) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM performance_objectives WHERE review_id = ? ORDER BY id",
        (review_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _fetch_competency_ratings(conn: sqlite3.Connection, review_id: int) -> List[dict]:
    rows = conn.execute(
        """SELECT r.*, c.code AS competency_code, c.name AS competency_name
           FROM performance_competency_ratings r
           JOIN competencies c ON c.id = r.competency_id
           WHERE r.review_id = ?
           ORDER BY c.id""",
        (review_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _active_competencies(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM competencies WHERE active = 1 ORDER BY id"
    ).fetchall()


def _touch_review(conn: sqlite3.Connection, review_id: int, **columns) -> None:
    """UPDATE helper. Column names come from module constants and literals in
    this file only — never from request data — so the f-string is safe."""
    set_clause = ", ".join(f"{k} = ?" for k in columns)
    conn.execute(
        f"UPDATE performance_reviews SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
        list(columns.values()) + [review_id],
    )


def _compute_scores(objectives: List[dict], comp_ratings: List[dict], role: str) -> dict:
    """Roll the individual 1-5 ratings up into the three frozen score columns.

    objective_score  = SUM(rating * weightage) / 100 — a weighted mean, which
                       lands back on the 1-5 scale because submit-objectives
                       guarantees the weightages total 100.
    competency_score = plain mean of the competency ratings (all core
                       competencies count equally — no weighting concept here).
    overall          = OBJECTIVES_WEIGHT * objective + COMPETENCIES_WEIGHT * competency
    """
    rating_col = f"{role}_rating"

    objective_score = round(
        sum(o[rating_col] * o["weightage"] for o in objectives) / TOTAL_WEIGHTAGE, 2
    ) if objectives else None

    rated = [c[rating_col] for c in comp_ratings if c[rating_col] is not None]
    competency_score = round(sum(rated) / len(rated), 2) if rated else None

    # Both halves are only ever None in degenerate configurations (no
    # objectives can't happen post-approval; no active competencies could, if
    # every competency were retired mid-cycle). Fall back to whichever half
    # exists rather than reporting a score computed from a partial formula.
    if objective_score is not None and competency_score is not None:
        overall = round(OBJECTIVES_WEIGHT * objective_score + COMPETENCIES_WEIGHT * competency_score, 2)
    else:
        overall = objective_score if objective_score is not None else competency_score

    return {
        f"{role}_objective_score": objective_score,
        f"{role}_competency_score": competency_score,
        f"{role}_overall_rating": overall,
    }


# ============================================================
# Competencies (read-only reference data)
# ============================================================

@router.get("/competencies", response_model=List[Competency])
def list_competencies(active: Optional[bool] = Query(None, description="Filter to active (or retired) competencies")):
    """The pre-defined company core competencies every appraisal is rated
    against. Read-only by design — see app/schemas/performance.py."""
    conn = get_connection()
    try:
        query = "SELECT * FROM competencies WHERE 1=1"
        params: list = []
        if active is not None:
            query += " AND active = ?"
            params.append(int(active))
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        return [dict(r, active=bool(r["active"])) for r in rows]
    finally:
        conn.close()


# ============================================================
# Reviews
# ============================================================

@router.get("/reviews", response_model=List[PerformanceReview])
def list_reviews(
    employee_id: Optional[str] = Query(None),
    manager_id: Optional[str] = Query(None, description="The reviewing manager — use this for a manager's action queue"),
    cycle_year: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="Draft, Objectives Submitted, Objectives Sent Back, Objectives Approved, Self Assessment Submitted, Completed"),
    stage: Optional[str] = Query(None, description="Objective Setting, Appraisal, Completed — derived from status"),
):
    """List/search reviews. The two common calls are 'this employee's review
    history' (`employee_id`) and 'what's sitting in my queue as a manager'
    (`manager_id` + `status`)."""
    conn = get_connection()
    try:
        query = "SELECT * FROM performance_reviews WHERE 1=1"
        params: list = []
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if manager_id:
            query += " AND manager_id = ?"
            params.append(manager_id)
        if cycle_year:
            query += " AND cycle_year = ?"
            params.append(cycle_year)
        if status:
            query += " AND status = ?"
            params.append(status)
        if stage:
            # `stage` isn't a column — expand it back into the statuses it covers.
            statuses = [s for s, st in STAGE_BY_STATUS.items() if st == stage]
            if not statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown stage '{stage}'; expected one of {sorted(set(STAGE_BY_STATUS.values()))}",
                )
            query += f" AND status IN ({','.join('?' * len(statuses))})"
            params.extend(statuses)
        query += " ORDER BY cycle_year DESC, employee_id"
        rows = conn.execute(query, params).fetchall()
        return [_review_response(r) for r in rows]
    finally:
        conn.close()


@router.get("/reviews/{review_ref}", response_model=PerformanceReviewDetail)
def get_review(review_ref: str):
    """Fetch one review with its objectives and competency ratings. This is
    the call a manager makes before assessing — the employee's self ratings
    and notes are right there alongside the manager's own columns."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        return dict(
            _review_response(review),
            objectives=_fetch_objectives(conn, review["id"]),
            competencies=_fetch_competency_ratings(conn, review["id"]),
        )
    finally:
        conn.close()


@router.post("/reviews", response_model=PerformanceReview, status_code=201)
def create_review(payload: PerformanceReviewCreate):
    """Open a review cycle for an employee. Always starts at status='Draft'
    (never caller-suppliable, same as a ticket's 'Open') so every later
    transition goes through the workflow endpoints and their guards.

    The reviewing manager is snapshotted from the employee's current
    `manager_id` — an employee with no manager (top of the org) can't have a
    review here, since there'd be nobody to approve objectives."""
    conn = get_connection()
    try:
        emp = _require_employee(conn, payload.employee_id)
        if emp["status"] == "Terminated":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot open a review cycle for terminated employee '{payload.employee_id}'",
            )
        if not emp["manager_id"]:
            raise HTTPException(
                status_code=400,
                detail=(f"Employee '{payload.employee_id}' has no manager; "
                        "a performance review needs a manager to review objectives."),
            )

        existing = conn.execute(
            "SELECT review_ref FROM performance_reviews WHERE employee_id = ? AND cycle_year = ?",
            (payload.employee_id, payload.cycle_year),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(f"Review already exists for '{payload.employee_id}' for {payload.cycle_year} "
                        f"({existing['review_ref']})"),
            )

        # Same ref shape as payslip_ref (PS-2026-06-E2043) — derived from
        # business keys, so no post-insert fixup is needed here.
        ref = f"PR-{payload.cycle_year}-{payload.employee_id.replace('E-', 'E')}"
        conn.execute(
            """
            INSERT INTO performance_reviews (review_ref, employee_id, manager_id, cycle_year, status)
            VALUES (?,?,?,?, 'Draft')
            """,
            (ref, payload.employee_id, emp["manager_id"], payload.cycle_year),
        )
        conn.commit()

        return _review_response(_require_review(conn, ref))
    finally:
        conn.close()


@router.delete("/reviews/{review_ref}", status_code=204)
def delete_review(review_ref: str):
    """Hard delete — mainly for test cleanup. Objectives and competency
    ratings go with it via ON DELETE CASCADE."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        conn.execute("DELETE FROM performance_reviews WHERE id = ?", (review["id"],))
        conn.commit()
        return None
    finally:
        conn.close()


# ============================================================
# Objective Setting phase
# ============================================================

@router.get("/reviews/{review_ref}/objectives", response_model=List[Objective])
def list_objectives(review_ref: str):
    """List the objectives set (or being set) for a review."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        return _fetch_objectives(conn, review["id"])
    finally:
        conn.close()


@router.post("/reviews/{review_ref}/objectives", response_model=Objective, status_code=201)
def add_objective(review_ref: str, payload: ObjectiveCreate):
    """Add an objective. Allowed only while the review is with the employee
    (Draft, or Objectives Sent Back after a manager rejection) — once
    submitted or approved the objective set is frozen.

    Weightage is NOT validated to total 100 here: objectives are added one at
    a time, so the running total is legitimately incomplete until the
    employee is done. That check belongs to submit-objectives."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        _require_status(review, *OBJECTIVE_EDITABLE_STATUSES)

        cur = conn.execute(
            "INSERT INTO performance_objectives (review_id, description, weightage) VALUES (?,?,?)",
            (review["id"], payload.description, payload.weightage),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM performance_objectives WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.patch("/objectives/{objective_id}", response_model=Objective)
def update_objective(objective_id: int, payload: ObjectiveUpdate):
    """Edit an objective's description/weightage — the typical follow-up to a
    manager sending objectives back with notes. Ratings aren't editable here;
    they belong to the assessment endpoints."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM performance_objectives WHERE id = ?", (objective_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Objective {objective_id} not found")

        review = conn.execute(
            "SELECT * FROM performance_reviews WHERE id = ?", (existing["review_id"],)
        ).fetchone()
        _require_status(review, *OBJECTIVE_EDITABLE_STATUSES)

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE performance_objectives SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            list(updates.values()) + [objective_id],
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM performance_objectives WHERE id = ?", (objective_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/objectives/{objective_id}", status_code=204)
def delete_objective(objective_id: int):
    """Remove an objective. Same status guard as editing one — an approved
    objective set can't be changed, which is what makes the frozen scores on
    the review meaningful."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM performance_objectives WHERE id = ?", (objective_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Objective {objective_id} not found")

        review = conn.execute(
            "SELECT * FROM performance_reviews WHERE id = ?", (existing["review_id"],)
        ).fetchone()
        _require_status(review, *OBJECTIVE_EDITABLE_STATUSES)

        conn.execute("DELETE FROM performance_objectives WHERE id = ?", (objective_id,))
        conn.commit()
        return None
    finally:
        conn.close()


@router.post("/reviews/{review_ref}/submit-objectives", response_model=PerformanceReview)
def submit_objectives(review_ref: str):
    """Employee action: send the objectives to the manager for approval.

    Requires at least one objective and weightages totalling exactly 100 —
    this is the only place that total is enforced, and enforcing it here is
    what lets the appraisal-phase weighted score be a plain 1-5 number.
    Also used to re-submit after a send-back."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        _require_status(review, *OBJECTIVE_EDITABLE_STATUSES)

        objectives = _fetch_objectives(conn, review["id"])
        if not objectives:
            raise HTTPException(
                status_code=400,
                detail=f"Review '{review_ref}' has no objectives to submit.",
            )
        total = sum(o["weightage"] for o in objectives)
        if total != TOTAL_WEIGHTAGE:
            raise HTTPException(
                status_code=400,
                detail=(f"Objective weightages must total {TOTAL_WEIGHTAGE}, "
                        f"got {total} across {len(objectives)} objective(s)."),
            )

        _touch_review(
            conn, review["id"],
            status="Objectives Submitted",
            objectives_submitted_at=_now(),
        )
        conn.commit()
        return _review_response(_require_review(conn, review_ref))
    finally:
        conn.close()


@router.post("/reviews/{review_ref}/review-objectives", response_model=PerformanceReview)
def review_objectives(review_ref: str, payload: ObjectiveReviewRequest):
    """Manager action: approve the submitted objectives, or send them back
    with notes for the employee to revise.

    `notes` is required on 'Send Back' (there's no point returning work
    without saying why) and optional on 'Approve'. Either way it overwrites
    `objectives_manager_notes` — approving without notes deliberately clears
    a stale send-back reason rather than leaving it on an approved review."""
    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        _require_status(review, "Objectives Submitted")

        if payload.decision == "Send Back" and not payload.notes:
            raise HTTPException(
                status_code=400,
                detail="`notes` is required when sending objectives back — the employee needs to know what to change.",
            )

        if payload.decision == "Approve":
            _touch_review(
                conn, review["id"],
                status="Objectives Approved",
                objectives_approved_at=_now(),
                objectives_manager_notes=payload.notes,
            )
        else:
            _touch_review(
                conn, review["id"],
                status="Objectives Sent Back",
                objectives_manager_notes=payload.notes,
            )
        conn.commit()
        return _review_response(_require_review(conn, review_ref))
    finally:
        conn.close()


# ============================================================
# Appraisal phase
# ============================================================

def _save_assessment(review_ref: str, payload: AssessmentRequest, role: str) -> dict:
    """Shared body of the self- and manager-assessment endpoints. Both rate
    the same objectives and the same core competencies; only the columns
    written (`self_*` vs `manager_*`) and the status transition differ.

    `role` is a literal from the two call sites below, never request data, so
    interpolating it into column names is safe."""
    config = ASSESSMENT_ROLES[role]
    rating_col, notes_col = f"{role}_rating", f"{role}_notes"

    conn = get_connection()
    try:
        review = _require_review(conn, review_ref)
        _require_status(review, config["required_status"])

        objectives = {o["id"]: o for o in _fetch_objectives(conn, review["id"])}
        competencies = {c["code"]: c for c in _active_competencies(conn)}

        # Validate the whole payload before writing anything — a partially
        # applied assessment would be worse than a rejected one.
        seen_objectives = set()
        for item in payload.objectives:
            if item.objective_id not in objectives:
                raise HTTPException(
                    status_code=400,
                    detail=f"Objective {item.objective_id} does not belong to review '{review_ref}'",
                )
            if item.objective_id in seen_objectives:
                raise HTTPException(
                    status_code=400,
                    detail=f"Objective {item.objective_id} rated more than once in the same request",
                )
            seen_objectives.add(item.objective_id)

        seen_competencies = set()
        for item in payload.competencies:
            if item.competency_code not in competencies:
                raise HTTPException(
                    status_code=400,
                    detail=(f"Unknown or retired competency '{item.competency_code}'; "
                            f"active codes are {sorted(competencies)}"),
                )
            if item.competency_code in seen_competencies:
                raise HTTPException(
                    status_code=400,
                    detail=f"Competency '{item.competency_code}' rated more than once in the same request",
                )
            seen_competencies.add(item.competency_code)

        for item in payload.objectives:
            conn.execute(
                f"""UPDATE performance_objectives
                    SET {rating_col} = ?, {notes_col} = ?, updated_at = datetime('now')
                    WHERE id = ?""",
                (item.rating, item.notes, item.objective_id),
            )

        for item in payload.competencies:
            # Rating rows are created lazily, so the first save for a
            # competency inserts and later ones update. The self side
            # normally inserts; the manager side normally updates.
            conn.execute(
                f"""INSERT INTO performance_competency_ratings
                        (review_id, competency_id, {rating_col}, {notes_col})
                    VALUES (?,?,?,?)
                    ON CONFLICT(review_id, competency_id) DO UPDATE SET
                        {rating_col} = excluded.{rating_col},
                        {notes_col} = excluded.{notes_col},
                        updated_at = datetime('now')""",
                (review["id"], competencies[item.competency_code]["id"], item.rating, item.notes),
            )

        if payload.submit:
            # Re-read post-write so completeness is checked against what's
            # actually stored, not just what this request happened to carry —
            # an earlier submit=False save counts toward completeness.
            saved_objectives = _fetch_objectives(conn, review["id"])
            saved_ratings = _fetch_competency_ratings(conn, review["id"])

            missing_objectives = [o["id"] for o in saved_objectives if o[rating_col] is None]
            rated_codes = {c["competency_code"] for c in saved_ratings if c[rating_col] is not None}
            missing_competencies = [code for code in competencies if code not in rated_codes]
            if missing_objectives or missing_competencies:
                conn.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=(f"Cannot submit: unrated objective ids {missing_objectives} and "
                            f"unrated competencies {missing_competencies}. "
                            "Rate everything, or send `submit: false` to save progress."),
                )

            _touch_review(
                conn, review["id"],
                status=config["submitted_status"],
                **{config["timestamp_column"]: _now()},
                **_compute_scores(saved_objectives, saved_ratings, role),
            )

        conn.commit()
        review = _require_review(conn, review_ref)
        return dict(
            _review_response(review),
            objectives=_fetch_objectives(conn, review["id"]),
            competencies=_fetch_competency_ratings(conn, review["id"]),
        )
    finally:
        conn.close()


@router.post("/reviews/{review_ref}/self-assessment", response_model=PerformanceReviewDetail)
def submit_self_assessment(review_ref: str, payload: AssessmentRequest):
    """Employee action: rate each approved objective and each core competency
    1-5 with optional notes, then send it to the manager.

    Requires the objectives to have been approved first — the appraisal is
    against the agreed objective set, so there's nothing to self-assess
    until the Objective Setting stage is done. Send `submit: false` to save
    a partial draft and come back to it."""
    return _save_assessment(review_ref, payload, "self")


@router.post("/reviews/{review_ref}/manager-assessment", response_model=PerformanceReviewDetail)
def submit_manager_assessment(review_ref: str, payload: AssessmentRequest):
    """Manager action: give their own 1-5 rating and notes for the same
    objectives and competencies, then submit — which completes the review.

    The employee's ratings are visible throughout (GET the review, or read
    the `self_*` fields on the response here) but are never modified by this
    call; the two sets of ratings sit side by side on the same rows."""
    return _save_assessment(review_ref, payload, "manager")
