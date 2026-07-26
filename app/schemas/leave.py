from pydantic import BaseModel
from typing import Optional, Literal

# Literal (not plain str) because finance.py's payslip deduction calc does an
# exact string match on leave_type == "Unpaid" and status == "Approved" — a
# typo here should 422 at the API boundary rather than silently produce a
# wrong salary deduction. Same class of justification as helpdesk's
# webhook-driven Literal (Priority/Status), different downstream consumer.
LeaveType = Literal["Annual", "Sick", "Unpaid", "Other"]
LeaveStatus = Literal["Approved", "Rejected", "Cancelled"]


class LeaveRequestBase(BaseModel):
    employee_id: str
    leave_type: LeaveType
    start_date: str
    end_date: str
    reason: Optional[str] = None


class LeaveRequestCreate(LeaveRequestBase):
    # Unlike TicketCreate, status IS required here — there is no approval
    # workflow in this app, so the caller states the final outcome directly.
    status: LeaveStatus
    # days intentionally excluded — always server-computed from start/end_date.


class LeaveRequestUpdate(BaseModel):
    """Partial update. employee_id is intentionally omitted: who a leave
    request belongs to is immutable after creation (mirrors requester_id on
    tickets). Changing start_date/end_date recomputes `days` server-side."""
    leave_type: Optional[LeaveType] = None
    status: Optional[LeaveStatus] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reason: Optional[str] = None


class LeaveRequest(LeaveRequestBase):
    id: int
    leave_id: str
    status: LeaveStatus
    days: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
