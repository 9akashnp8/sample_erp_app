from pydantic import BaseModel
from typing import Optional, Literal

# Literal (not plain str, unlike this app's other status-like fields) because
# these values drive an outbound webhook to an external agent app — invalid
# values should 422 at the API boundary rather than silently propagate
# downstream. `category` stays plain str (open-ended, like `department`).
Priority = Literal["Low", "Medium", "High", "Urgent"]
Status = Literal["Open", "In Progress", "Resolved", "Closed"]


class TicketBase(BaseModel):
    subject: str
    description: str
    requester_id: str
    assignee_id: Optional[str] = None
    category: str = "General"  # IT, HR, Finance, Facilities, General
    priority: Priority = "Medium"


class TicketCreate(TicketBase):
    pass  # status intentionally excluded — server always creates as "Open"


class TicketUpdate(BaseModel):
    """All fields optional — PATCH-style partial update. requester_id is
    intentionally omitted: who filed a ticket is immutable after creation."""
    subject: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None  # explicit null is a valid "unassign"
    category: Optional[str] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None


class Ticket(TicketBase):
    id: int
    ticket_id: str
    status: Status
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
