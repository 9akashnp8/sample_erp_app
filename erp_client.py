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

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ERPClientError(resp.status_code, detail)
        if resp.status_code == 204:
            return None
        return resp.json()

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
