from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date


class EmployeeBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    job_title: str
    department: str
    manager_id: Optional[str] = None
    employment_type: str = Field(default="Full-Time")  # Full-Time, Part-Time, Contractor, Intern
    status: str = Field(default="Active")               # Active, On Leave, Terminated
    hire_date: date
    termination_date: Optional[date] = None
    location: Optional[str] = None
    phone: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    employee_id: str  # business id, e.g. "E-5001"; caller supplies it (or see auto-generate note in router)


class EmployeeUpdate(BaseModel):
    """All fields optional — PATCH-style partial update."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    manager_id: Optional[str] = None
    employment_type: Optional[str] = None
    status: Optional[str] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    location: Optional[str] = None
    phone: Optional[str] = None


class Employee(EmployeeBase):
    id: int
    employee_id: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
