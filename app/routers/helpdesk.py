import json
import os
import sqlite3
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.schemas.helpdesk import Ticket, TicketCreate, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["Helpdesk"])

TICKET_WEBHOOK_URL = os.environ.get("TICKET_WEBHOOK_URL")
TICKET_WEBHOOK_SECRET = os.environ.get("TICKET_WEBHOOK_SECRET")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _require_employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    emp = conn.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
    return emp


def _dispatch_webhook(event: str, ticket: dict, changes: Optional[dict] = None) -> None:
    """Synchronous, best-effort, fire-after-commit. Never raises — a dead or
    unconfigured webhook target must never fail or roll back the ticket write.
    No retry/outbox: a failed dispatch is logged and dropped."""
    if not TICKET_WEBHOOK_URL:
        return
    body = {
        "event": event,
        # matches the `datetime('now')` string shape used elsewhere in this app
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "ticket": ticket,
    }
    if changes is not None:
        body["changes"] = changes
    headers = {"Content-Type": "application/json"}
    if TICKET_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = TICKET_WEBHOOK_SECRET
    try:
        req = urllib.request.Request(
            TICKET_WEBHOOK_URL, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"[helpdesk webhook] dispatch failed for event={event} ticket_id={ticket.get('ticket_id')}: {e}")


@router.get("", response_model=List[Ticket])
def list_tickets(
    status: Optional[str] = Query(None, description="Open, In Progress, Resolved, Closed"),
    priority: Optional[str] = Query(None, description="Low, Medium, High, Urgent"),
    category: Optional[str] = Query(None),
    requester_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search subject/description"),
):
    """List/search tickets with optional filters."""
    conn = get_connection()
    try:
        query = "SELECT * FROM tickets WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if category:
            query += " AND category = ?"
            params.append(category)
        if requester_id:
            query += " AND requester_id = ?"
            params.append(requester_id)
        if assignee_id:
            query += " AND assignee_id = ?"
            params.append(assignee_id)
        if q:
            query += " AND (subject LIKE ? OR description LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like])
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str):
    """Fetch a single ticket by its ticket_id."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.post("", response_model=Ticket, status_code=201)
def create_ticket(payload: TicketCreate):
    """File a new ticket. Always created with status='Open' — the initial
    status is never caller-suppliable (see app/schemas/helpdesk.py), so every
    later status transition goes through the PATCH diff logic that fires
    the ticket.status_changed webhook event."""
    conn = get_connection()
    try:
        _require_employee(conn, payload.requester_id)
        if payload.assignee_id is not None:
            _require_employee(conn, payload.assignee_id)

        # ticket_id depends on the autoincrement id, which SQLite only assigns
        # after the INSERT — unlike payslip_ref, this needs two statements
        # before one commit: insert with a placeholder, then update by lastrowid.
        placeholder = f"PENDING-{uuid.uuid4().hex}"
        cur = conn.execute(
            """
            INSERT INTO tickets
            (ticket_id, subject, description, requester_id, assignee_id, category, priority, status)
            VALUES (?,?,?,?,?,?,?, 'Open')
            """,
            (placeholder, payload.subject, payload.description, payload.requester_id,
             payload.assignee_id, payload.category, payload.priority),
        )
        ticket_ref = f"TCK-{cur.lastrowid:06d}"
        conn.execute("UPDATE tickets SET ticket_id = ? WHERE id = ?", (ticket_ref, cur.lastrowid))
        conn.commit()

        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (cur.lastrowid,)).fetchone()
        ticket = _row_to_dict(row)
        _dispatch_webhook("ticket.created", ticket)
        return ticket
    finally:
        conn.close()


@router.patch("/{ticket_id}", response_model=Ticket)
def update_ticket(ticket_id: str, payload: TicketUpdate):
    """Partial update — assignment and status changes both go through this
    endpoint (mirrors how employee status changes go through PATCH, not
    dedicated action endpoints). A single call that changes both `status`
    and `assignee_id` fires two separate webhook events after commit."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        if "assignee_id" in updates and updates["assignee_id"] is not None:
            _require_employee(conn, updates["assignee_id"])

        # Timestamp special-casing, applied before the generic SET clause is
        # built (same style as update_bank_account's is_primary handling).
        # History is preserved: resolved_at/closed_at are never cleared on reopen.
        new_status = updates.get("status")
        if new_status == "Resolved":
            updates["resolved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        elif new_status == "Closed":
            updates["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if existing["resolved_at"] is None:
                updates["resolved_at"] = updates["closed_at"]

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [ticket_id]
        conn.execute(
            f"UPDATE tickets SET {set_clause}, updated_at = datetime('now') WHERE ticket_id = ?",
            values,
        )
        conn.commit()

        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        ticket = _row_to_dict(row)

        if "status" in updates and updates["status"] != existing["status"]:
            _dispatch_webhook(
                "ticket.status_changed", ticket,
                changes={"status": {"old": existing["status"], "new": updates["status"]}},
            )
        if "assignee_id" in updates and updates["assignee_id"] != existing["assignee_id"]:
            _dispatch_webhook(
                "ticket.assigned", ticket,
                changes={"assignee_id": {"old": existing["assignee_id"], "new": updates["assignee_id"]}},
            )
        return ticket
    finally:
        conn.close()


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: str):
    """Hard delete — mainly for test cleanup. Prefer PATCH status='Closed' in
    practice. Intentionally does NOT dispatch a webhook: deletions are
    test-harness cleanup, not real ticket lifecycle events."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT 1 FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
        conn.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
        conn.commit()
        return None
    finally:
        conn.close()
