from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import sqlite3

from app.database import get_connection
from app.schemas.employee import Employee, EmployeeCreate, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["Employees"])


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


@router.get("", response_model=List[Employee])
def list_employees(
    department: Optional[str] = Query(None, description="Filter by department, e.g. Engineering"),
    status: Optional[str] = Query(None, description="Filter by status: Active, On Leave, Terminated"),
    manager_id: Optional[str] = Query(None, description="Filter by direct manager's employee_id"),
    q: Optional[str] = Query(None, description="Search by name or email (partial match)"),
):
    """List employees with optional filters. This is the general-purpose lookup
    an agent should use for questions like 'who is on the Engineering team' or
    'find employees named Priya'."""
    conn = get_connection()
    try:
        query = "SELECT * FROM employees WHERE 1=1"
        params: list = []

        if department:
            query += " AND department = ?"
            params.append(department)
        if status:
            query += " AND status = ?"
            params.append(status)
        if manager_id:
            query += " AND manager_id = ?"
            params.append(manager_id)
        if q:
            query += " AND (first_name LIKE ? OR last_name LIKE ? OR email LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like])

        query += " ORDER BY employee_id"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{employee_id}", response_model=Employee)
def get_employee(employee_id: str):
    """Fetch a single employee profile by business employee_id (e.g. E-2043)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.get("/{employee_id}/direct-reports", response_model=List[Employee])
def get_direct_reports(employee_id: str):
    """Return everyone who reports directly to this employee_id. Useful for
    manager-scoped queries, e.g. 'show me my team's leave requests'."""
    conn = get_connection()
    try:
        manager = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not manager:
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")

        rows = conn.execute(
            "SELECT * FROM employees WHERE manager_id = ? ORDER BY employee_id", (employee_id,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("", response_model=Employee, status_code=201)
def create_employee(payload: EmployeeCreate):
    """Onboard a new employee profile."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM employees WHERE employee_id = ? OR email = ?",
            (payload.employee_id, payload.email),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="employee_id or email already exists")

        if payload.manager_id:
            mgr = conn.execute(
                "SELECT 1 FROM employees WHERE employee_id = ?", (payload.manager_id,)
            ).fetchone()
            if not mgr:
                raise HTTPException(status_code=400, detail=f"manager_id '{payload.manager_id}' does not exist")

        conn.execute(
            """
            INSERT INTO employees
            (employee_id, first_name, last_name, email, job_title, department,
             manager_id, employment_type, status, hire_date, termination_date, location, phone)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.employee_id, payload.first_name, payload.last_name, payload.email,
                payload.job_title, payload.department, payload.manager_id,
                payload.employment_type, payload.status, str(payload.hire_date),
                str(payload.termination_date) if payload.termination_date else None,
                payload.location, payload.phone,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (payload.employee_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.patch("/{employee_id}", response_model=Employee)
def update_employee(employee_id: str, payload: EmployeeUpdate):
    """Partial update — e.g. change department, status, manager, or mark terminated."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        if "manager_id" in updates and updates["manager_id"]:
            mgr = conn.execute(
                "SELECT 1 FROM employees WHERE employee_id = ?", (updates["manager_id"],)
            ).fetchone()
            if not mgr:
                raise HTTPException(status_code=400, detail=f"manager_id '{updates['manager_id']}' does not exist")

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = [str(v) if not isinstance(v, str) and v is not None else v for v in updates.values()]
        values.append(employee_id)

        conn.execute(
            f"UPDATE employees SET {set_clause}, updated_at = datetime('now') WHERE employee_id = ?",
            values,
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{employee_id}", status_code=204)
def delete_employee(employee_id: str):
    """Hard delete — provided for test cleanup. In a real ERP you would almost
    always prefer PATCH status='Terminated' over deleting the record."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")

        conn.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))
        conn.commit()
        return None
    finally:
        conn.close()
