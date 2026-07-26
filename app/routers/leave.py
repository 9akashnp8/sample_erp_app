import sqlite3
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.schemas.leave import LeaveRequest, LeaveRequestCreate, LeaveRequestUpdate

router = APIRouter(prefix="/leave-requests", tags=["Leave"])


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _require_employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    emp = conn.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
    return emp


def _calc_days(start_date: str, end_date: str) -> int:
    d1, d2 = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if d2 < d1:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    return (d2 - d1).days + 1


def _period_bounds(period_year: int, period_month: int) -> tuple:
    start = f"{period_year:04d}-{period_month:02d}-01"
    nxt = (f"{period_year + 1:04d}-01-01" if period_month == 12
           else f"{period_year:04d}-{period_month + 1:02d}-01")
    return start, nxt


@router.get("", response_model=List[LeaveRequest])
def list_leave_requests(
    employee_id: Optional[str] = Query(None),
    leave_type: Optional[str] = Query(None, description="Annual, Sick, Unpaid, Other"),
    status: Optional[str] = Query(None, description="Approved, Rejected, Cancelled"),
    period_year: Optional[int] = Query(None),
    period_month: Optional[int] = Query(None, ge=1, le=12, description="Filters by start_date falling in this month"),
):
    """List/search leave requests with optional filters."""
    conn = get_connection()
    try:
        query = "SELECT * FROM leave_requests WHERE 1=1"
        params: list = []
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if leave_type:
            query += " AND leave_type = ?"
            params.append(leave_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if period_year and period_month:
            start, nxt = _period_bounds(period_year, period_month)
            query += " AND start_date >= ? AND start_date < ?"
            params.extend([start, nxt])
        query += " ORDER BY start_date DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{leave_id}", response_model=LeaveRequest)
def get_leave_request(leave_id: str):
    """Fetch a single leave request by its leave_id."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM leave_requests WHERE leave_id = ?", (leave_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Leave request '{leave_id}' not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.post("", response_model=LeaveRequest, status_code=201)
def create_leave_request(payload: LeaveRequestCreate):
    """Create a leave request already in its final state — there is no
    approval workflow modeled in this app, so `status` is required and
    caller-supplied directly (unlike tickets, where status is server-only)."""
    conn = get_connection()
    try:
        _require_employee(conn, payload.employee_id)
        days = _calc_days(payload.start_date, payload.end_date)

        # leave_id depends on the autoincrement id, which SQLite only assigns
        # after the INSERT — same two-step pattern as ticket_id in helpdesk.py.
        placeholder = "PENDING"
        cur = conn.execute(
            """
            INSERT INTO leave_requests
            (leave_id, employee_id, leave_type, status, start_date, end_date, days, reason)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (placeholder, payload.employee_id, payload.leave_type, payload.status,
             payload.start_date, payload.end_date, days, payload.reason),
        )
        leave_ref = f"LV-{cur.lastrowid:06d}"
        conn.execute("UPDATE leave_requests SET leave_id = ? WHERE id = ?", (leave_ref, cur.lastrowid))
        conn.commit()

        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.patch("/{leave_id}", response_model=LeaveRequest)
def update_leave_request(leave_id: str, payload: LeaveRequestUpdate):
    """Partial update. If either start_date or end_date is supplied, `days`
    is recomputed against the merged (existing + new) date pair."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM leave_requests WHERE leave_id = ?", (leave_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Leave request '{leave_id}' not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        if "start_date" in updates or "end_date" in updates:
            new_start = updates.get("start_date", existing["start_date"])
            new_end = updates.get("end_date", existing["end_date"])
            updates["days"] = _calc_days(new_start, new_end)

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [leave_id]
        conn.execute(
            f"UPDATE leave_requests SET {set_clause}, updated_at = datetime('now') WHERE leave_id = ?",
            values,
        )
        conn.commit()

        row = conn.execute("SELECT * FROM leave_requests WHERE leave_id = ?", (leave_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{leave_id}", status_code=204)
def delete_leave_request(leave_id: str):
    """Hard delete — mainly for test cleanup."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT 1 FROM leave_requests WHERE leave_id = ?", (leave_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Leave request '{leave_id}' not found")
        conn.execute("DELETE FROM leave_requests WHERE leave_id = ?", (leave_id,))
        conn.commit()
        return None
    finally:
        conn.close()
