"""
ERP Client — the ONLY thing your agents should import.

Agents call functions here, not the database or FastAPI routers directly.
When you get access to the real ERP, change ERP_BASE_URL (env var or the
default below) and, if needed, adjust the request/response mapping inside
each function. Agent code that calls these functions does not change.

Usage:
    from erp_client import ERPClient
    erp = ERPClient()  # or ERPClient(base_url="https://real-erp.company.com/api")
    employee = erp.get_employee("E-2043")
    reports  = erp.get_direct_reports("E-3320")
"""
import os
from typing import Optional, List, Dict, Any
import requests

ERP_BASE_URL = os.environ.get("ERP_BASE_URL", "http://localhost:8000")


class ERPClientError(Exception):
    """Raised when the ERP API returns an error response."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"ERP API error {status_code}: {detail}")


class ERPClient:
    def __init__(self, base_url: str = ERP_BASE_URL, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _send(self, method: str, path: str, **kwargs):
        """Issue the call and turn any error status into an ERPClientError.
        Shared by the JSON and binary paths — an error body is JSON either way."""
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ERPClientError(resp.status_code, detail)
        return resp

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self._send(method, path, **kwargs)
        if resp.status_code == 204:
            return None
        return resp.json()

    def _request_bytes(self, method: str, path: str, **kwargs) -> bytes:
        """For endpoints that return a file rather than JSON — currently only
        the issued letter PDF."""
        return self._send(method, path, **kwargs).content

    # ---------- Employee module ----------

    def get_employee(self, employee_id: str) -> Dict[str, Any]:
        """Fetch a single employee profile by employee_id."""
        return self._request("GET", f"/employees/{employee_id}")

    def list_employees(
        self,
        department: Optional[str] = None,
        status: Optional[str] = None,
        manager_id: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List/search employees with optional filters."""
        params = {k: v for k, v in {
            "department": department, "status": status,
            "manager_id": manager_id, "q": q,
        }.items() if v is not None}
        return self._request("GET", "/employees", params=params)

    def get_direct_reports(self, employee_id: str) -> List[Dict[str, Any]]:
        """List employees who report directly to the given manager's employee_id."""
        return self._request("GET", f"/employees/{employee_id}/direct-reports")

    def create_employee(self, **fields) -> Dict[str, Any]:
        """Onboard a new employee. Required fields: employee_id, first_name,
        last_name, email, job_title, department, hire_date. Optional: manager_id,
        employment_type, status, location, phone."""
        return self._request("POST", "/employees", json=fields)

    def update_employee(self, employee_id: str, **fields) -> Dict[str, Any]:
        """Partial update of any employee field(s), e.g.
        update_employee('E-2043', department='Sales', manager_id='E-1001')."""
        return self._request("PATCH", f"/employees/{employee_id}", json=fields)

    def terminate_employee(self, employee_id: str, termination_date: str) -> Dict[str, Any]:
        """Convenience wrapper — marks status='Terminated' and sets the date."""
        return self.update_employee(
            employee_id, status="Terminated", termination_date=termination_date
        )

    def delete_employee(self, employee_id: str) -> None:
        """Hard delete — mainly for test cleanup. Prefer terminate_employee()."""
        self._request("DELETE", f"/employees/{employee_id}")

    # ---------- Finance module ----------

    def get_bank_accounts(self, employee_id: str) -> List[Dict[str, Any]]:
        """List bank accounts for an employee. Only masked account numbers
        are ever returned — the full number is never exposed by this API."""
        return self._request("GET", "/finance/bank-accounts", params={"employee_id": employee_id})

    def add_bank_account(self, employee_id: str, bank_name: str, account_holder_name: str,
                          account_number: str, currency: str = "USD",
                          iban: Optional[str] = None, swift_bic: Optional[str] = None,
                          is_primary: bool = True) -> Dict[str, Any]:
        """Add a bank account. account_number is masked + 'encrypted' server-side
        and the raw value is never returned afterward."""
        payload = {
            "employee_id": employee_id, "bank_name": bank_name,
            "account_holder_name": account_holder_name, "account_number": account_number,
            "currency": currency, "iban": iban, "swift_bic": swift_bic,
            "is_primary": is_primary,
        }
        return self._request("POST", "/finance/bank-accounts", json=payload)

    def update_bank_account(self, account_id: int, **fields) -> Dict[str, Any]:
        """Partial update of a bank account, e.g. update_bank_account(16, status='Inactive')."""
        return self._request("PATCH", f"/finance/bank-accounts/{account_id}", json=fields)

    def get_salary_info(self, employee_id: str) -> Dict[str, Any]:
        """Fetch an employee's current gross salary record."""
        return self._request("GET", f"/finance/salary/{employee_id}")

    def set_salary_info(self, employee_id: str, gross_salary: float, currency: str,
                         effective_date: str, pay_frequency: str = "Monthly") -> Dict[str, Any]:
        """Create the initial salary record for an employee (fails if one already exists —
        use update_salary_info for raises/changes)."""
        payload = {
            "employee_id": employee_id, "gross_salary": gross_salary,
            "currency": currency, "effective_date": effective_date,
            "pay_frequency": pay_frequency,
        }
        return self._request("POST", "/finance/salary", json=payload)

    def update_salary_info(self, employee_id: str, **fields) -> Dict[str, Any]:
        """Partial update, e.g. update_salary_info('E-2043', gross_salary=12500) for a raise."""
        return self._request("PATCH", f"/finance/salary/{employee_id}", json=fields)

    def list_payslips(self, employee_id: Optional[str] = None,
                       period_year: Optional[int] = None,
                       period_month: Optional[int] = None) -> List[Dict[str, Any]]:
        """List payslips, optionally filtered by employee and/or period."""
        params = {k: v for k, v in {
            "employee_id": employee_id, "period_year": period_year,
            "period_month": period_month,
        }.items() if v is not None}
        return self._request("GET", "/finance/payslips", params=params)

    def get_payslip(self, payslip_ref: str) -> Dict[str, Any]:
        """Fetch a single payslip by its reference, e.g. 'PS-2026-06-E2043'."""
        return self._request("GET", f"/finance/payslips/{payslip_ref}")

    def generate_payslip(self, employee_id: str, period_month: int, period_year: int,
                          other_deductions: float = 0, other_deductions_note: Optional[str] = None,
                          tax_deduction: Optional[float] = None) -> Dict[str, Any]:
        """Generate a payslip for an employee/period from their current salary_info.
        Fails (409) if a payslip already exists for that employee+period, or (400)
        if the employee has no salary record yet."""
        payload = {
            "employee_id": employee_id, "period_month": period_month, "period_year": period_year,
            "other_deductions": other_deductions, "other_deductions_note": other_deductions_note,
            "tax_deduction": tax_deduction,
        }
        return self._request("POST", "/finance/payslips/generate", json=payload)

    # ---------- Helpdesk module ----------

    def create_ticket(self, subject: str, description: str, requester_id: str,
                       assignee_id: Optional[str] = None, category: str = "General",
                       priority: str = "Medium") -> Dict[str, Any]:
        """File a new ticket. Always created with status='Open'."""
        payload = {
            "subject": subject, "description": description, "requester_id": requester_id,
            "assignee_id": assignee_id, "category": category, "priority": priority,
        }
        return self._request("POST", "/tickets", json=payload)

    def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Fetch a single ticket by its ticket_id, e.g. 'TCK-000042'."""
        return self._request("GET", f"/tickets/{ticket_id}")

    def list_tickets(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        requester_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List/search tickets with optional filters."""
        params = {k: v for k, v in {
            "status": status, "priority": priority, "category": category,
            "requester_id": requester_id, "assignee_id": assignee_id, "q": q,
        }.items() if v is not None}
        return self._request("GET", "/tickets", params=params)

    def update_ticket(self, ticket_id: str, **fields) -> Dict[str, Any]:
        """Partial update of any ticket field(s), e.g.
        update_ticket('TCK-000042', priority='High')."""
        return self._request("PATCH", f"/tickets/{ticket_id}", json=fields)

    def assign_ticket(self, ticket_id: str, assignee_id: str) -> Dict[str, Any]:
        """Convenience wrapper — assigns (or reassigns) a ticket to an employee."""
        return self.update_ticket(ticket_id, assignee_id=assignee_id)

    def resolve_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Convenience wrapper — marks status='Resolved'."""
        return self.update_ticket(ticket_id, status="Resolved")

    def close_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Convenience wrapper — marks status='Closed'."""
        return self.update_ticket(ticket_id, status="Closed")

    def reopen_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Convenience wrapper — marks status='Open'."""
        return self.update_ticket(ticket_id, status="Open")

    def delete_ticket(self, ticket_id: str) -> None:
        """Hard delete — mainly for test cleanup. Prefer close_ticket()."""
        self._request("DELETE", f"/tickets/{ticket_id}")

    # ---------- Leave module ----------

    def create_leave_request(self, employee_id: str, leave_type: str, status: str,
                              start_date: str, end_date: str,
                              reason: Optional[str] = None) -> Dict[str, Any]:
        """Create a leave request already in its final state (Approved/Rejected/
        Cancelled) — there is no approval workflow, so status is required."""
        payload = {
            "employee_id": employee_id, "leave_type": leave_type, "status": status,
            "start_date": start_date, "end_date": end_date, "reason": reason,
        }
        return self._request("POST", "/leave-requests", json=payload)

    def get_leave_request(self, leave_id: str) -> Dict[str, Any]:
        """Fetch a single leave request by its leave_id, e.g. 'LV-000012'."""
        return self._request("GET", f"/leave-requests/{leave_id}")

    def list_leave_requests(
        self,
        employee_id: Optional[str] = None,
        leave_type: Optional[str] = None,
        status: Optional[str] = None,
        period_year: Optional[int] = None,
        period_month: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List/search leave requests with optional filters."""
        params = {k: v for k, v in {
            "employee_id": employee_id, "leave_type": leave_type, "status": status,
            "period_year": period_year, "period_month": period_month,
        }.items() if v is not None}
        return self._request("GET", "/leave-requests", params=params)

    def update_leave_request(self, leave_id: str, **fields) -> Dict[str, Any]:
        """Partial update of any leave request field(s), e.g.
        update_leave_request('LV-000012', status='Rejected')."""
        return self._request("PATCH", f"/leave-requests/{leave_id}", json=fields)

    def cancel_leave_request(self, leave_id: str) -> Dict[str, Any]:
        """Convenience wrapper — marks status='Cancelled'."""
        return self.update_leave_request(leave_id, status="Cancelled")

    def delete_leave_request(self, leave_id: str) -> None:
        """Hard delete — mainly for test cleanup."""
        self._request("DELETE", f"/leave-requests/{leave_id}")

    # ---------- Letters & certificates module ----------

    def request_letter(self, employee_id: str, include_salary: bool = False,
                        include_bank_details: bool = False,
                        addressed_to: Optional[str] = None,
                        purpose: Optional[str] = None,
                        letter_type: str = "For Whom It May Concern") -> Dict[str, Any]:
        """Submit a 'For Whom It May Concern' request from self-service. Always
        comes back Pending — HR still has to issue it before there is a PDF.

        The three variants are: plain (neither flag), with salary
        (include_salary), and with salary + bank details (both).
        include_bank_details alone is a 422 — the bank paragraph exists to say
        where the salary is credited."""
        payload = {
            "employee_id": employee_id, "letter_type": letter_type,
            "include_salary": include_salary, "include_bank_details": include_bank_details,
            "addressed_to": addressed_to, "purpose": purpose,
        }
        return self._request("POST", "/letters/requests", json=payload)

    def get_letter_request(self, request_ref: str) -> Dict[str, Any]:
        """Fetch a single letter request by its request_ref, e.g. 'LC-000012'."""
        return self._request("GET", f"/letters/requests/{request_ref}")

    def list_letter_requests(self, employee_id: Optional[str] = None,
                              status: Optional[str] = None,
                              letter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List/search letter requests — an employee's own history, or HR's
        queue (status='Pending'). Newest first."""
        params = {k: v for k, v in {
            "employee_id": employee_id, "status": status, "letter_type": letter_type,
        }.items() if v is not None}
        return self._request("GET", "/letters/requests", params=params)

    def update_letter_request(self, request_ref: str, **fields) -> Dict[str, Any]:
        """Amend a still-Pending request, e.g.
        update_letter_request('LC-000012', include_salary=True). 409 once the
        request has been issued/rejected/cancelled."""
        return self._request("PATCH", f"/letters/requests/{request_ref}", json=fields)

    def issue_letter_request(self, request_ref: str,
                              notes: Optional[str] = None) -> Dict[str, Any]:
        """HR action — issue the letter. This snapshots the employee's details
        (plus salary/bank if requested) onto the request and assigns a
        document_ref; the PDF is available from that point on. Fails with 400
        if the letter asks for salary/bank data the employee doesn't have."""
        return self._request("POST", f"/letters/requests/{request_ref}/issue",
                             json={"notes": notes})

    def reject_letter_request(self, request_ref: str, reason: str) -> Dict[str, Any]:
        """HR action — decline the request. `reason` is required."""
        return self._request("POST", f"/letters/requests/{request_ref}/reject",
                             json={"reason": reason})

    def cancel_letter_request(self, request_ref: str) -> Dict[str, Any]:
        """Employee action — withdraw a request HR hasn't acted on yet."""
        return self._request("POST", f"/letters/requests/{request_ref}/cancel")

    def get_letter_content(self, request_ref: str) -> Dict[str, Any]:
        """The issued letter as structured JSON — the same fields and
        paragraphs the PDF prints. Read this rather than parsing the PDF."""
        return self._request("GET", f"/letters/requests/{request_ref}/content")

    def download_letter_document(self, request_ref: str,
                                  save_to: Optional[str] = None) -> bytes:
        """Download the issued letter's PDF, optionally writing it to `save_to`.
        Returns the raw bytes either way. 409 unless the request is Issued."""
        content = self._request_bytes("GET", f"/letters/requests/{request_ref}/document")
        if save_to:
            with open(save_to, "wb") as f:
                f.write(content)
        return content

    def delete_letter_request(self, request_ref: str) -> None:
        """Hard delete — mainly for test cleanup. Prefer cancel/reject."""
        self._request("DELETE", f"/letters/requests/{request_ref}")

    # ---------- Performance management module ----------

    def list_competencies(self, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        """The pre-defined company core competencies every appraisal is rated
        against. Read-only — competencies are seed/reference data."""
        params = {} if active is None else {"active": active}
        return self._request("GET", "/performance/competencies", params=params)

    def create_performance_review(self, employee_id: str, cycle_year: int) -> Dict[str, Any]:
        """Open a review cycle. Starts at status='Draft'; the reviewing manager
        is snapshotted from the employee's current manager_id."""
        payload = {"employee_id": employee_id, "cycle_year": cycle_year}
        return self._request("POST", "/performance/reviews", json=payload)

    def get_performance_review(self, review_ref: str) -> Dict[str, Any]:
        """Fetch one review with its objectives and competency ratings —
        e.g. 'PR-2026-E2043'. Both sides' ratings come back on the same rows."""
        return self._request("GET", f"/performance/reviews/{review_ref}")

    def list_performance_reviews(
        self,
        employee_id: Optional[str] = None,
        manager_id: Optional[str] = None,
        cycle_year: Optional[int] = None,
        status: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List/search reviews. Pass manager_id (+ status) for a manager's
        action queue, employee_id for one person's review history."""
        params = {k: v for k, v in {
            "employee_id": employee_id, "manager_id": manager_id,
            "cycle_year": cycle_year, "status": status, "stage": stage,
        }.items() if v is not None}
        return self._request("GET", "/performance/reviews", params=params)

    def delete_performance_review(self, review_ref: str) -> None:
        """Hard delete — mainly for test cleanup. Objectives and competency
        ratings cascade with it."""
        self._request("DELETE", f"/performance/reviews/{review_ref}")

    # -- Objective setting phase --

    def list_objectives(self, review_ref: str) -> List[Dict[str, Any]]:
        """List the objectives set (or being set) for a review."""
        return self._request("GET", f"/performance/reviews/{review_ref}/objectives")

    def add_objective(self, review_ref: str, description: str, weightage: int) -> Dict[str, Any]:
        """Add an objective. Only allowed while the review is with the employee
        (status Draft or Objectives Sent Back)."""
        payload = {"description": description, "weightage": weightage}
        return self._request("POST", f"/performance/reviews/{review_ref}/objectives", json=payload)

    def update_objective(self, objective_id: int, **fields) -> Dict[str, Any]:
        """Partial update of an objective's description/weightage, e.g.
        update_objective(7, weightage=30). Ratings go through the assessment calls."""
        return self._request("PATCH", f"/performance/objectives/{objective_id}", json=fields)

    def delete_objective(self, objective_id: int) -> None:
        """Remove an objective (same status guard as editing one)."""
        self._request("DELETE", f"/performance/objectives/{objective_id}")

    def submit_objectives(self, review_ref: str) -> Dict[str, Any]:
        """Employee action — send objectives to the manager for approval.
        Fails (400) unless weightages total exactly 100."""
        return self._request("POST", f"/performance/reviews/{review_ref}/submit-objectives")

    def approve_objectives(self, review_ref: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Manager action — approve the submitted objectives, ending the
        objective setting phase and opening the appraisal phase."""
        return self._request(
            "POST", f"/performance/reviews/{review_ref}/review-objectives",
            json={"decision": "Approve", "notes": notes},
        )

    def send_back_objectives(self, review_ref: str, notes: str) -> Dict[str, Any]:
        """Manager action — return the objectives for revision. `notes` is
        required: the employee needs to know what to change."""
        return self._request(
            "POST", f"/performance/reviews/{review_ref}/review-objectives",
            json={"decision": "Send Back", "notes": notes},
        )

    # -- Appraisal phase --

    def submit_self_assessment(self, review_ref: str,
                                objectives: List[Dict[str, Any]],
                                competencies: List[Dict[str, Any]],
                                submit: bool = True) -> Dict[str, Any]:
        """Employee action — rate each objective and core competency 1-5.

        objectives:   [{"objective_id": 12, "rating": 4, "notes": "..."}, ...]
        competencies: [{"competency_code": "COLLAB", "rating": 5, "notes": "..."}, ...]

        submit=False saves a partial draft; submit=True requires everything to
        be rated and sends it to the manager."""
        payload = {"objectives": objectives, "competencies": competencies, "submit": submit}
        return self._request("POST", f"/performance/reviews/{review_ref}/self-assessment", json=payload)

    def submit_manager_assessment(self, review_ref: str,
                                   objectives: List[Dict[str, Any]],
                                   competencies: List[Dict[str, Any]],
                                   submit: bool = True) -> Dict[str, Any]:
        """Manager action — same payload shape as the self assessment, written
        to the manager_* columns. Submitting completes the review."""
        payload = {"objectives": objectives, "competencies": competencies, "submit": submit}
        return self._request("POST", f"/performance/reviews/{review_ref}/manager-assessment", json=payload)
