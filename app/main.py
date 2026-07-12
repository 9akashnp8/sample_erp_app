"""
ERP Sample App — entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000

Docs at http://localhost:8000/docs

As more modules are added (leave, tickets, payroll, ...), register their
routers below the same way employees is registered. Each module owns its
own table(s), router, and schema — agents built against this app can later
be pointed at a real ERP by swapping the base URL only; endpoint shapes
should stay stable.
"""
from fastapi import FastAPI

from app.routers import employees, finance

app = FastAPI(
    title="Sample ERP API",
    description="Minimal ERP backing store for HR automation agent testing.",
    version="0.1.0",
)

app.include_router(employees.router)
app.include_router(finance.router)


@app.get("/health", tags=["Meta"])
def health_check():
    return {"status": "ok"}
