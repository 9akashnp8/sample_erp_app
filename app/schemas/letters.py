from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal, List

# Literal for the same reason as performance's ReviewStatus: `status` gates
# which endpoints are legal on a request, so a typo should 422 at the API
# boundary rather than strand a request in a state nothing can move it out of.
LetterRequestStatus = Literal["Pending", "Issued", "Rejected", "Cancelled"]

# One value today. Kept as a Literal (rather than dropping the field) so the
# real ERP's other documents — Experience Letter, NOC, Salary Certificate —
# slot in here later without changing the request/response shape agents use.
LetterType = Literal["For Whom It May Concern"]


class LetterRequestCreate(BaseModel):
    """What an employee submits from self-service. `status` is intentionally
    absent — a request is always created Pending and only HR's issue/reject
    endpoints move it, the same server-owned-status rule as tickets and
    performance reviews (and the opposite of leave requests, which have no
    approval step to model)."""
    employee_id: str
    letter_type: LetterType = "For Whom It May Concern"
    include_salary: bool = Field(False, description="Adds the salary paragraph (gross, currency, pay frequency).")
    include_bank_details: bool = Field(False, description="Adds the bank paragraph. Requires include_salary — the bank details exist in the letter to say where that salary is credited.")
    addressed_to: Optional[str] = Field(None, description="e.g. 'The Consulate General of Canada'. Omit for a plain 'To Whom It May Concern'.")
    purpose: Optional[str] = Field(None, description="e.g. 'visa application' — printed in the closing paragraph.")

    @model_validator(mode="after")
    def bank_requires_salary(self):
        # Mirrors the CHECK constraint in db/schema_letters.sql. Validated here
        # too so the caller gets a 422 naming the field, not an opaque IntegrityError.
        if self.include_bank_details and not self.include_salary:
            raise ValueError("include_bank_details requires include_salary")
        return self


class LetterRequestUpdate(BaseModel):
    """Partial update — only while the request is still Pending (409 after
    that: an issued letter is a document that already exists). employee_id and
    letter_type are omitted deliberately; re-request instead of mutating what
    was asked for. The salary/bank dependency is re-checked in the router
    against the merged (existing + new) values."""
    include_salary: Optional[bool] = None
    include_bank_details: Optional[bool] = None
    addressed_to: Optional[str] = None
    purpose: Optional[str] = None


class LetterIssueRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional HR note stored on the request; never printed on the letter.")


class LetterRejectRequest(BaseModel):
    reason: str = Field(..., description="Required — the employee needs to know why, same rule as sending performance objectives back.")


class LetterRequest(BaseModel):
    """A request row. The snapshot_* fields are all NULL until the request is
    issued; the salary/bank ones stay NULL unless they were asked for."""
    id: int
    request_ref: str
    employee_id: str
    letter_type: LetterType
    include_salary: bool
    include_bank_details: bool
    addressed_to: Optional[str] = None
    purpose: Optional[str] = None
    status: LetterRequestStatus
    decision_notes: Optional[str] = None
    document_ref: Optional[str] = None
    issued_at: Optional[str] = None

    snapshot_full_name: Optional[str] = None
    snapshot_job_title: Optional[str] = None
    snapshot_department: Optional[str] = None
    snapshot_employment_type: Optional[str] = None
    snapshot_hire_date: Optional[str] = None
    snapshot_gross_salary: Optional[float] = None
    snapshot_currency: Optional[str] = None
    snapshot_pay_frequency: Optional[str] = None
    snapshot_bank_name: Optional[str] = None
    snapshot_account_holder_name: Optional[str] = None
    snapshot_masked_account_number: Optional[str] = None
    snapshot_iban: Optional[str] = None
    snapshot_swift_bic: Optional[str] = None

    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ---------------- Rendered document ----------------
# GET .../document returns the PDF itself; GET .../content returns this — the
# same composed letter as structured JSON. Both are built from one function in
# the router, so what an agent reads and what the employee downloads can't drift.
# The JSON view exists because agents reason over fields and sentences far more
# easily than over PDF bytes.

class LetterOrganization(BaseModel):
    name: str
    address: str


class LetterEmployeeDetails(BaseModel):
    employee_id: str
    full_name: str
    job_title: str
    department: str
    employment_type: str
    hire_date: str


class LetterSalaryDetails(BaseModel):
    gross_salary: float
    currency: str
    pay_frequency: str


class LetterBankDetails(BaseModel):
    """Masked account number only — this app never exposes a full one
    (see db/schema_letters.sql)."""
    bank_name: str
    account_holder_name: str
    masked_account_number: str
    iban: Optional[str] = None
    swift_bic: Optional[str] = None


class LetterDocument(BaseModel):
    request_ref: str
    document_ref: str
    letter_type: LetterType
    issued_at: str
    issue_date: str = Field(..., description="issued_at as the date printed on the letter, e.g. '08 September 2026'.")
    organization: LetterOrganization
    addressed_to: str = Field(..., description="Resolved salutation — the request's addressed_to, or 'To Whom It May Concern' when it was left blank. Printed uppercase as the letter's heading.")
    employee: LetterEmployeeDetails
    salary: Optional[LetterSalaryDetails] = None
    bank: Optional[LetterBankDetails] = None
    purpose: Optional[str] = None
    body: List[str] = Field(..., description="The letter's paragraphs in order, exactly as they appear in the PDF.")
    signatory: str
