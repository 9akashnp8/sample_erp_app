from pydantic import BaseModel, Field, field_validator
from typing import Optional


# ---------------- Bank Accounts ----------------

class BankAccountCreate(BaseModel):
    employee_id: str
    bank_name: str
    account_holder_name: str
    account_number: str = Field(..., description="Full account number — will be masked and 'encrypted' before storage, never stored or returned in plain form.")
    iban: Optional[str] = None
    swift_bic: Optional[str] = None
    currency: str = "USD"
    is_primary: bool = True


class BankAccountUpdate(BaseModel):
    bank_name: Optional[str] = None
    account_holder_name: Optional[str] = None
    account_number: Optional[str] = Field(None, description="If provided, replaces the stored account number (re-masked/re-encrypted).")
    iban: Optional[str] = None
    swift_bic: Optional[str] = None
    currency: Optional[str] = None
    is_primary: Optional[bool] = None
    status: Optional[str] = None


class BankAccount(BaseModel):
    """Response model — deliberately excludes encrypted_account_number.
    Only the masked number is ever returned by the API."""
    id: int
    employee_id: str
    bank_name: str
    account_holder_name: str
    masked_account_number: str
    iban: Optional[str] = None
    swift_bic: Optional[str] = None
    currency: str
    is_primary: bool
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ---------------- Salary Info ----------------

class SalaryInfoCreate(BaseModel):
    employee_id: str
    gross_salary: float = Field(..., gt=0)
    currency: str = "USD"
    pay_frequency: str = "Monthly"
    effective_date: str


class SalaryInfoUpdate(BaseModel):
    gross_salary: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = None
    pay_frequency: Optional[str] = None
    effective_date: Optional[str] = None


class SalaryInfo(BaseModel):
    id: int
    employee_id: str
    gross_salary: float
    currency: str
    pay_frequency: str
    effective_date: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ---------------- Payslips ----------------

class PayslipGenerateRequest(BaseModel):
    employee_id: str
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2000, le=2100)
    tax_deduction: Optional[float] = Field(None, description="Override computed tax deduction, if supplied.")
    other_deductions: float = Field(0, ge=0)
    other_deductions_note: Optional[str] = None

    @field_validator("period_year")
    @classmethod
    def year_sane(cls, v):
        return v


class Payslip(BaseModel):
    id: int
    payslip_ref: str
    employee_id: str
    period_month: int
    period_year: int
    gross_salary: float
    tax_deduction: float
    other_deductions: float
    other_deductions_note: Optional[str] = None
    unpaid_leave_days: int
    leave_deduction: float
    net_pay: float
    currency: str
    status: str
    generated_at: str

    class Config:
        from_attributes = True
