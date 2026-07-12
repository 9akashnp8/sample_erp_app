import hashlib
import sqlite3
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from app.database import get_connection
from app.schemas.finance import (
    BankAccount, BankAccountCreate, BankAccountUpdate,
    SalaryInfo, SalaryInfoCreate, SalaryInfoUpdate,
    Payslip, PayslipGenerateRequest,
)

router = APIRouter(prefix="/finance", tags=["Finance"])

TAX_RATE = 0.18  # flat sample rate used when tax_deduction isn't explicitly supplied


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _fake_encrypt(raw: str) -> str:
    """Placeholder 'encryption' — NOT real crypto, mirrors scripts/build_finance.py.
    Swap for a real encryption/KMS call when wiring to a production ERP."""
    return "enc_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _require_employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    emp = conn.execute(
        "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")
    return emp


# ============================================================
# Bank Accounts
# ============================================================

@router.get("/bank-accounts", response_model=List[BankAccount])
def list_bank_accounts(
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Active or Inactive"),
):
    """List bank accounts. Never returns the encrypted/full account number —
    only the masked form. Filter by employee_id for the common case of
    'what account does this employee get paid into'."""
    conn = get_connection()
    try:
        query = """SELECT id, employee_id, bank_name, account_holder_name,
                          masked_account_number, iban, swift_bic, currency,
                          is_primary, status, created_at, updated_at
                   FROM bank_accounts WHERE 1=1"""
        params: list = []
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY employee_id, is_primary DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r, is_primary=bool(r["is_primary"])) for r in rows]
    finally:
        conn.close()


@router.get("/bank-accounts/{account_id}", response_model=BankAccount)
def get_bank_account(account_id: int):
    """Fetch one bank account by its internal id. Masked number only."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT id, employee_id, bank_name, account_holder_name,
                      masked_account_number, iban, swift_bic, currency,
                      is_primary, status, created_at, updated_at
               FROM bank_accounts WHERE id = ?""",
            (account_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Bank account {account_id} not found")
        return dict(row, is_primary=bool(row["is_primary"]))
    finally:
        conn.close()


@router.post("/bank-accounts", response_model=BankAccount, status_code=201)
def create_bank_account(payload: BankAccountCreate):
    """Add a bank account for an employee. The raw account_number supplied
    here is masked + 'encrypted' before storage and is never returned by any
    endpoint — only the masked form is retrievable afterward."""
    conn = get_connection()
    try:
        _require_employee(conn, payload.employee_id)

        masked = "****" + payload.account_number[-4:]
        encrypted = _fake_encrypt(payload.account_number)

        if payload.is_primary:
            conn.execute(
                "UPDATE bank_accounts SET is_primary = 0 WHERE employee_id = ?",
                (payload.employee_id,),
            )

        cur = conn.execute(
            """
            INSERT INTO bank_accounts
            (employee_id, bank_name, account_holder_name, masked_account_number,
             encrypted_account_number, iban, swift_bic, currency, is_primary, status)
            VALUES (?,?,?,?,?,?,?,?,?, 'Active')
            """,
            (payload.employee_id, payload.bank_name, payload.account_holder_name,
             masked, encrypted, payload.iban, payload.swift_bic, payload.currency,
             int(payload.is_primary)),
        )
        conn.commit()

        row = conn.execute(
            """SELECT id, employee_id, bank_name, account_holder_name,
                      masked_account_number, iban, swift_bic, currency,
                      is_primary, status, created_at, updated_at
               FROM bank_accounts WHERE id = ?""",
            (cur.lastrowid,),
        ).fetchone()
        return dict(row, is_primary=bool(row["is_primary"]))
    finally:
        conn.close()


@router.patch("/bank-accounts/{account_id}", response_model=BankAccount)
def update_bank_account(account_id: int, payload: BankAccountUpdate):
    """Partial update. Supplying account_number re-masks and re-'encrypts' it."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM bank_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Bank account {account_id} not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return dict(existing, is_primary=bool(existing["is_primary"]))

        if "account_number" in updates:
            raw = updates.pop("account_number")
            updates["masked_account_number"] = "****" + raw[-4:]
            updates["encrypted_account_number"] = _fake_encrypt(raw)

        if updates.get("is_primary"):
            conn.execute(
                "UPDATE bank_accounts SET is_primary = 0 WHERE employee_id = ? AND id != ?",
                (existing["employee_id"], account_id),
            )

        if "is_primary" in updates:
            updates["is_primary"] = int(updates["is_primary"])

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [account_id]
        conn.execute(
            f"UPDATE bank_accounts SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        conn.commit()

        row = conn.execute(
            """SELECT id, employee_id, bank_name, account_holder_name,
                      masked_account_number, iban, swift_bic, currency,
                      is_primary, status, created_at, updated_at
               FROM bank_accounts WHERE id = ?""",
            (account_id,),
        ).fetchone()
        return dict(row, is_primary=bool(row["is_primary"]))
    finally:
        conn.close()


@router.delete("/bank-accounts/{account_id}", status_code=204)
def delete_bank_account(account_id: int):
    """Hard delete — mainly for test cleanup. Prefer PATCH status='Inactive' in practice."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM bank_accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Bank account {account_id} not found")
        conn.execute("DELETE FROM bank_accounts WHERE id = ?", (account_id,))
        conn.commit()
        return None
    finally:
        conn.close()


# ============================================================
# Salary Info
# ============================================================

@router.get("/salary/{employee_id}", response_model=SalaryInfo)
def get_salary_info(employee_id: str):
    """Fetch the current salary record for an employee."""
    conn = get_connection()
    try:
        _require_employee(conn, employee_id)
        row = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No salary record for '{employee_id}'")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.post("/salary", response_model=SalaryInfo, status_code=201)
def create_salary_info(payload: SalaryInfoCreate):
    """Set the salary record for an employee. Fails if one already exists —
    use PATCH /finance/salary/{employee_id} to change it."""
    conn = get_connection()
    try:
        _require_employee(conn, payload.employee_id)
        existing = conn.execute(
            "SELECT 1 FROM salary_info WHERE employee_id = ?", (payload.employee_id,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Salary record already exists for '{payload.employee_id}'; use PATCH to update it.",
            )

        conn.execute(
            """
            INSERT INTO salary_info (employee_id, gross_salary, currency, pay_frequency, effective_date)
            VALUES (?,?,?,?,?)
            """,
            (payload.employee_id, payload.gross_salary, payload.currency,
             payload.pay_frequency, payload.effective_date),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (payload.employee_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.patch("/salary/{employee_id}", response_model=SalaryInfo)
def update_salary_info(employee_id: str, payload: SalaryInfoUpdate):
    """Update an employee's salary (e.g. a raise). Partial update."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"No salary record for '{employee_id}'")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [employee_id]
        conn.execute(
            f"UPDATE salary_info SET {set_clause}, updated_at = datetime('now') WHERE employee_id = ?",
            values,
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# ============================================================
# Payslips
# ============================================================

@router.get("/payslips", response_model=List[Payslip])
def list_payslips(
    employee_id: Optional[str] = Query(None),
    period_year: Optional[int] = Query(None),
    period_month: Optional[int] = Query(None, ge=1, le=12),
):
    """List payslips with optional filters — the typical calls are
    'all payslips for employee X' or 'payslip for employee X in period Y/M'."""
    conn = get_connection()
    try:
        query = "SELECT * FROM payslips WHERE 1=1"
        params: list = []
        if employee_id:
            query += " AND employee_id = ?"
            params.append(employee_id)
        if period_year:
            query += " AND period_year = ?"
            params.append(period_year)
        if period_month:
            query += " AND period_month = ?"
            params.append(period_month)
        query += " ORDER BY period_year DESC, period_month DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/payslips/{payslip_ref}", response_model=Payslip)
def get_payslip(payslip_ref: str):
    """Fetch a single payslip by its reference (e.g. PS-2026-06-E2043)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM payslips WHERE payslip_ref = ?", (payslip_ref,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Payslip '{payslip_ref}' not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.post("/payslips/generate", response_model=Payslip, status_code=201)
def generate_payslip(payload: PayslipGenerateRequest):
    """Generate a payslip for an employee for a given month/year, computed
    from their current salary_info. Fails with 409 if a payslip already
    exists for that employee+period (re-generation isn't allowed here —
    a real system would version or require an explicit override)."""
    conn = get_connection()
    try:
        emp = _require_employee(conn, payload.employee_id)

        salary = conn.execute(
            "SELECT * FROM salary_info WHERE employee_id = ?", (payload.employee_id,)
        ).fetchone()
        if not salary:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate payslip: no salary record for '{payload.employee_id}'",
            )

        existing = conn.execute(
            "SELECT 1 FROM payslips WHERE employee_id = ? AND period_month = ? AND period_year = ?",
            (payload.employee_id, payload.period_month, payload.period_year),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(f"Payslip already exists for '{payload.employee_id}' "
                        f"for {payload.period_year}-{payload.period_month:02d}"),
            )

        gross = salary["gross_salary"]
        currency = salary["currency"]
        tax = payload.tax_deduction if payload.tax_deduction is not None else round(gross * TAX_RATE, 2)
        other = payload.other_deductions
        net = round(gross - tax - other, 2)

        ref = f"PS-{payload.period_year}-{payload.period_month:02d}-{payload.employee_id.replace('E-', 'E')}"

        conn.execute(
            """
            INSERT INTO payslips
            (payslip_ref, employee_id, period_month, period_year, gross_salary,
             tax_deduction, other_deductions, other_deductions_note, net_pay,
             currency, status, generated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?, 'Generated', datetime('now'))
            """,
            (ref, payload.employee_id, payload.period_month, payload.period_year, gross,
             tax, other, payload.other_deductions_note, net, currency),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM payslips WHERE payslip_ref = ?", (ref,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/payslips/{payslip_ref}", status_code=204)
def delete_payslip(payslip_ref: str):
    """Hard delete — for test cleanup only."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM payslips WHERE payslip_ref = ?", (payslip_ref,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Payslip '{payslip_ref}' not found")
        conn.execute("DELETE FROM payslips WHERE payslip_ref = ?", (payslip_ref,))
        conn.commit()
        return None
    finally:
        conn.close()
