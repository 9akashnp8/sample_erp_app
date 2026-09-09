import sqlite3
from datetime import date, datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Response

from app.database import get_connection
from app.pdf_writer import render_pdf, text, space, rule
from app.schemas.letters import (
    LetterRequest, LetterRequestCreate, LetterRequestUpdate,
    LetterIssueRequest, LetterRejectRequest, LetterDocument,
)

router = APIRouter(prefix="/letters", tags=["Letters & Certificates"])

# Letterhead constants — the sample organization these mock records belong to
# (matches the acmecorp.example addresses in scripts/build_employees.py). Same
# flat-constant style as finance.py's TAX_RATE; a real ERP reads this from a
# company profile table.
ORGANIZATION_NAME = "Acme Corporation"
ORGANIZATION_ADDRESS = "400 Park Avenue, New York, NY 10022, United States"
SIGNATORY = "Human Resources"

DEFAULT_ADDRESSEE = "To Whom It May Concern"

# Short code used in document_ref. Keyed by letter_type so a second document
# type is a one-line addition here plus a body template in _compose_letter.
LETTER_TYPE_CODES = {"For Whom It May Concern": "FWIMC"}

# Columns written by the issue endpoint, in the order _snapshot() returns them.
SNAPSHOT_COLUMNS = (
    "snapshot_full_name", "snapshot_job_title", "snapshot_department",
    "snapshot_employment_type", "snapshot_hire_date",
    "snapshot_gross_salary", "snapshot_currency", "snapshot_pay_frequency",
    "snapshot_bank_name", "snapshot_account_holder_name",
    "snapshot_masked_account_number", "snapshot_iban", "snapshot_swift_bic",
)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """SQLite has no boolean type — the include_* flags come back as 0/1 and are
    converted here, same as finance.py does for bank_accounts.is_primary."""
    return dict(row,
                include_salary=bool(row["include_salary"]),
                include_bank_details=bool(row["include_bank_details"]))


def _now() -> str:
    """Matches the `datetime('now')` string shape used elsewhere in this app."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _long_date(value: str) -> str:
    """'2026-09-08' or '2026-09-08 11:20:00' -> '08 September 2026', the form a
    letter prints. Dates are stored ISO everywhere else in this app."""
    return date.fromisoformat(value[:10]).strftime("%d %B %Y")


def _money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _require_employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    emp = conn.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
    return emp


def _require_current_employment(emp: sqlite3.Row) -> None:
    """A 'For Whom It May Concern' letter certifies *current* employment, so a
    terminated employee can't have one — in the real ERP they no longer have a
    self-service login at all. 400 rather than 404: the employee exists, the
    request just isn't a valid thing to ask for. What a terminated employee
    needs is an experience letter, which this module doesn't model yet."""
    if emp["status"] == "Terminated":
        ended = f" as of {emp['termination_date']}" if emp["termination_date"] else ""
        raise HTTPException(
            status_code=400,
            detail=(f"Employee '{emp['employee_id']}' is Terminated{ended} — a "
                    "For Whom It May Concern letter certifies current employment."),
        )


def _require_request(conn: sqlite3.Connection, request_ref: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM letter_requests WHERE request_ref = ?", (request_ref,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Letter request '{request_ref}' not found")
    return row


def _require_status(request: sqlite3.Row, *allowed: str) -> None:
    """409 on an out-of-order transition — the request is well-formed, it's the
    current state that conflicts (same reasoning as performance.py)."""
    if request["status"] not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(f"Letter request '{request['request_ref']}' is in status "
                    f"'{request['status']}'; this action requires status "
                    f"{' or '.join(repr(s) for s in allowed)}."),
        )


def _snapshot(conn: sqlite3.Connection, emp: sqlite3.Row,
              include_salary: bool, include_bank_details: bool) -> tuple:
    """Freeze the details the letter will print, in SNAPSHOT_COLUMNS order.

    Missing salary/bank data is a 400 at issue time rather than a letter with a
    blank paragraph — the same 'can't generate from data that isn't there' rule
    finance.py applies when generating a payslip without salary_info."""
    values = [f"{emp['first_name']} {emp['last_name']}", emp["job_title"],
              emp["department"], emp["employment_type"], emp["hire_date"]]

    if include_salary:
        salary = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (emp["employee_id"],)
        ).fetchone()
        if not salary:
            raise HTTPException(
                status_code=400,
                detail=("Cannot issue with salary details: no salary record for "
                        f"'{emp['employee_id']}'"),
            )
        values += [salary["gross_salary"], salary["currency"], salary["pay_frequency"]]
    else:
        values += [None, None, None]

    if include_bank_details:
        # The account the salary is actually credited to: primary first, and
        # only Active ones — an Inactive account is a closed account.
        account = conn.execute(
            """SELECT * FROM bank_accounts
               WHERE employee_id = ? AND status = 'Active'
               ORDER BY is_primary DESC, id LIMIT 1""",
            (emp["employee_id"],),
        ).fetchone()
        if not account:
            raise HTTPException(
                status_code=400,
                detail=("Cannot issue with bank details: no active bank account for "
                        f"'{emp['employee_id']}'"),
            )
        values += [account["bank_name"], account["account_holder_name"],
                   account["masked_account_number"], account["iban"], account["swift_bic"]]
    else:
        values += [None, None, None, None, None]

    return tuple(values)


def _compose_letter(row: sqlite3.Row) -> dict:
    """Build the issued document from the snapshot — never from live employee,
    salary or bank data. Single source for both the JSON view and the PDF, so
    the two can never say different things."""
    addressee = row["addressed_to"] or DEFAULT_ADDRESSEE
    full_name = row["snapshot_full_name"]

    # Written without pronouns throughout: this app doesn't record gender, and
    # guessing one on an official letter is worse than not using one at all.
    body = [
        (f"This is to certify that {full_name} (Employee ID: {row['employee_id']}) "
         f"has been employed with {ORGANIZATION_NAME} as {row['snapshot_job_title']} "
         f"in the {row['snapshot_department']} department since "
         f"{_long_date(row['snapshot_hire_date'])}, on a "
         f"{row['snapshot_employment_type']} basis."),
    ]

    salary = None
    if row["include_salary"]:
        salary = {
            "gross_salary": row["snapshot_gross_salary"],
            "currency": row["snapshot_currency"],
            "pay_frequency": row["snapshot_pay_frequency"],
        }
        body.append(
            f"The current gross salary is {_money(salary['gross_salary'], salary['currency'])}, "
            f"payable {salary['pay_frequency'].lower()}."
        )

    bank = None
    if row["include_bank_details"]:
        bank = {
            "bank_name": row["snapshot_bank_name"],
            "account_holder_name": row["snapshot_account_holder_name"],
            "masked_account_number": row["snapshot_masked_account_number"],
            "iban": row["snapshot_iban"],
            "swift_bic": row["snapshot_swift_bic"],
        }
        sentence = (f"This salary is credited to account {bank['masked_account_number']} "
                    f"held with {bank['bank_name']} in the name of "
                    f"{bank['account_holder_name']}.")
        if bank["iban"]:
            sentence += f" IBAN: {bank['iban']}."
        if bank["swift_bic"]:
            sentence += f" SWIFT/BIC: {bank['swift_bic']}."
        body.append(sentence)

    purpose_clause = f" for the purpose of {row['purpose']}." if row["purpose"] else "."
    body.append(f"This letter has been issued at the employee's request{purpose_clause}")
    body.append(f"For any verification of the above, please contact the {SIGNATORY} "
                f"department of {ORGANIZATION_NAME}.")

    return {
        "request_ref": row["request_ref"],
        "document_ref": row["document_ref"],
        "letter_type": row["letter_type"],
        "issued_at": row["issued_at"],
        "issue_date": _long_date(row["issued_at"]),
        "organization": {"name": ORGANIZATION_NAME, "address": ORGANIZATION_ADDRESS},
        "addressed_to": addressee,
        "employee": {
            "employee_id": row["employee_id"],
            "full_name": full_name,
            "job_title": row["snapshot_job_title"],
            "department": row["snapshot_department"],
            "employment_type": row["snapshot_employment_type"],
            "hire_date": row["snapshot_hire_date"],
        },
        "salary": salary,
        "bank": bank,
        "purpose": row["purpose"],
        "body": body,
        "signatory": f"{SIGNATORY}, {ORGANIZATION_NAME}",
    }


def _letter_pdf(letter: dict) -> bytes:
    """Lay the composed letter out as a PDF — letterhead, reference block,
    heading, the same body paragraphs the JSON view returns, then the signoff."""
    blocks = [
        text(letter["organization"]["name"], font="bold", size=17),
        text(letter["organization"]["address"], size=9, leading=12),
        rule(),
        space(14),
        text(f"Ref: {letter['document_ref']}", size=10, leading=13),
        text(f"Date: {letter['issue_date']}", size=10, leading=13),
        space(18),
        text(letter["addressed_to"].upper(), font="bold", size=12),
        space(14),
    ]
    for paragraph in letter["body"]:
        blocks += [text(paragraph), space(8)]
    blocks += [
        space(14),
        text("Sincerely,"),
        space(30),  # room for a signature
        text(letter["signatory"], font="bold"),
    ]
    return render_pdf(blocks)


# ============================================================
# Requests
# ============================================================

@router.get("/requests", response_model=List[LetterRequest])
def list_letter_requests(
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Pending, Issued, Rejected, Cancelled"),
    letter_type: Optional[str] = Query(None, description="For Whom It May Concern"),
):
    """List/search letter requests — typically one employee's own history, or
    HR's queue of everything still Pending."""
    conn = get_connection()
    try:
        query = "SELECT * FROM letter_requests WHERE 1=1"
        params: list = []
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if letter_type:
            query += " AND letter_type = ?"
            params.append(letter_type)
        query += " ORDER BY created_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/requests/{request_ref}", response_model=LetterRequest)
def get_letter_request(request_ref: str):
    """Fetch a single letter request by its request_ref, e.g. 'LC-000012'."""
    conn = get_connection()
    try:
        return _row_to_dict(_require_request(conn, request_ref))
    finally:
        conn.close()


@router.post("/requests", response_model=LetterRequest, status_code=201)
def create_letter_request(payload: LetterRequestCreate):
    """Submit a request from self-service. Always created Pending — HR then
    issues or rejects it. Nothing is snapshotted yet: the letter's contents are
    read at issue time, so a raise between request and issue is reflected."""
    conn = get_connection()
    try:
        emp = _require_employee(conn, payload.employee_id)
        _require_current_employment(emp)

        # request_ref depends on the autoincrement id, which SQLite only
        # assigns after the INSERT — same two-step pattern as leave/helpdesk.
        cur = conn.execute(
            """
            INSERT INTO letter_requests
            (request_ref, employee_id, letter_type, include_salary,
             include_bank_details, addressed_to, purpose, status)
            VALUES (?,?,?,?,?,?,?, 'Pending')
            """,
            ("PENDING", payload.employee_id, payload.letter_type,
             int(payload.include_salary), int(payload.include_bank_details),
             payload.addressed_to, payload.purpose),
        )
        request_ref = f"LC-{cur.lastrowid:06d}"
        conn.execute("UPDATE letter_requests SET request_ref = ? WHERE id = ?",
                     (request_ref, cur.lastrowid))
        conn.commit()

        row = conn.execute("SELECT * FROM letter_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.patch("/requests/{request_ref}", response_model=LetterRequest)
def update_letter_request(request_ref: str, payload: LetterRequestUpdate):
    """Amend a request before HR acts on it — e.g. the employee realises the
    embassy wants salary details too. Pending only (409 otherwise): an issued
    letter is a document that already exists, and re-editing what it was
    supposed to say would make the stored snapshot a lie. `status` is not
    settable here — use the issue/reject/cancel endpoints."""
    conn = get_connection()
    try:
        existing = _require_request(conn, request_ref)
        _require_status(existing, "Pending")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        # Re-check the dependency against the merged values: dropping salary
        # from a request that includes bank details is just as invalid as
        # adding bank details without salary (see db/schema_letters.sql).
        merged_salary = updates.get("include_salary", bool(existing["include_salary"]))
        merged_bank = updates.get("include_bank_details", bool(existing["include_bank_details"]))
        if merged_bank and not merged_salary:
            raise HTTPException(
                status_code=400, detail="include_bank_details requires include_salary"
            )

        for flag in ("include_salary", "include_bank_details"):
            if flag in updates:
                updates[flag] = int(updates[flag])

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        conn.execute(
            f"UPDATE letter_requests SET {set_clause}, updated_at = datetime('now') "
            "WHERE request_ref = ?",
            list(updates.values()) + [request_ref],
        )
        conn.commit()

        return _row_to_dict(_require_request(conn, request_ref))
    finally:
        conn.close()


@router.delete("/requests/{request_ref}", status_code=204)
def delete_letter_request(request_ref: str):
    """Hard delete — mainly for test cleanup. Prefer cancel/reject, which keep
    the audit trail an HR module is supposed to have."""
    conn = get_connection()
    try:
        _require_request(conn, request_ref)
        conn.execute("DELETE FROM letter_requests WHERE request_ref = ?", (request_ref,))
        conn.commit()
        return None
    finally:
        conn.close()


# ============================================================
# Workflow: Pending -> Issued / Rejected / Cancelled
# ============================================================

@router.post("/requests/{request_ref}/issue", response_model=LetterRequest)
def issue_letter_request(request_ref: str, payload: LetterIssueRequest = LetterIssueRequest()):
    """HR action — approve the request and bring the document into existence.

    This is where the employee/salary/bank details are read and frozen onto the
    request, and where document_ref is assigned. The PDF itself is rendered on
    demand from that snapshot rather than stored, so it stays reproducible for
    as long as the row survives."""
    conn = get_connection()
    try:
        existing = _require_request(conn, request_ref)
        _require_status(existing, "Pending")

        emp = _require_employee(conn, existing["employee_id"])
        _require_current_employment(emp)
        snapshot = _snapshot(conn, emp, bool(existing["include_salary"]),
                             bool(existing["include_bank_details"]))

        issued_at = _now()
        code = LETTER_TYPE_CODES[existing["letter_type"]]
        document_ref = (f"{code}-{issued_at[:4]}-"
                        f"{existing['employee_id'].replace('E-', 'E')}-{existing['id']:06d}")

        set_snapshot = ", ".join(f"{c} = ?" for c in SNAPSHOT_COLUMNS)
        conn.execute(
            f"""UPDATE letter_requests
                SET status = 'Issued', document_ref = ?, issued_at = ?,
                    decision_notes = ?, {set_snapshot}, updated_at = datetime('now')
                WHERE request_ref = ?""",
            (document_ref, issued_at, payload.notes, *snapshot, request_ref),
        )
        conn.commit()

        return _row_to_dict(_require_request(conn, request_ref))
    finally:
        conn.close()


@router.post("/requests/{request_ref}/reject", response_model=LetterRequest)
def reject_letter_request(request_ref: str, payload: LetterRejectRequest):
    """HR action — decline the request. `reason` is required: the employee
    needs to know what to change before re-requesting."""
    conn = get_connection()
    try:
        existing = _require_request(conn, request_ref)
        _require_status(existing, "Pending")

        conn.execute(
            """UPDATE letter_requests
               SET status = 'Rejected', decision_notes = ?, updated_at = datetime('now')
               WHERE request_ref = ?""",
            (payload.reason, request_ref),
        )
        conn.commit()

        return _row_to_dict(_require_request(conn, request_ref))
    finally:
        conn.close()


@router.post("/requests/{request_ref}/cancel", response_model=LetterRequest)
def cancel_letter_request(request_ref: str):
    """Employee action — withdraw a request HR hasn't acted on yet. There is no
    un-issue: once a letter exists, it has left the building."""
    conn = get_connection()
    try:
        existing = _require_request(conn, request_ref)
        _require_status(existing, "Pending")

        conn.execute(
            """UPDATE letter_requests
               SET status = 'Cancelled', updated_at = datetime('now')
               WHERE request_ref = ?""",
            (request_ref,),
        )
        conn.commit()

        return _row_to_dict(_require_request(conn, request_ref))
    finally:
        conn.close()


# ============================================================
# The document itself
# ============================================================

@router.get("/requests/{request_ref}/content", response_model=LetterDocument)
def get_letter_content(request_ref: str):
    """The issued letter as structured JSON — the same fields and the same
    paragraphs the PDF prints. Prefer this over parsing the PDF: agents read
    sentences and figures far more easily than PDF bytes."""
    conn = get_connection()
    try:
        row = _require_request(conn, request_ref)
        _require_status(row, "Issued")
        return _compose_letter(row)
    finally:
        conn.close()


@router.get(
    "/requests/{request_ref}/document",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}},
                     "description": "The issued letter as a PDF."}},
)
def download_letter_document(request_ref: str):
    """Download the issued letter as a PDF — what the employee gets back from
    self-service. Rendered on demand from the stored snapshot, so repeated
    downloads are identical. 409 while the request is Pending/Rejected/
    Cancelled: there is no document to download yet."""
    conn = get_connection()
    try:
        row = _require_request(conn, request_ref)
        _require_status(row, "Issued")
        filename = f"{row['document_ref']}.pdf"
        return Response(
            content=_letter_pdf(_compose_letter(row)),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()
