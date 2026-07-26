# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY erp_client.py .
COPY entrypoint.sh .

# Schema *.sql files are app code, not persisted data — bake them into the
# image at a path OUTSIDE the /app/db volume mount below. If they lived in
# /app/db, a named volume created on an earlier image (before a new module's
# schema file existed) would permanently shadow the whole directory on every
# rebuild, hiding newly-added schema files (e.g. a fresh module's
# schema_<module>.sql) even after `RESET_DB=1` — only `docker compose down -v`
# would reveal them. Keeping schema files here means a plain rebuild + RESET_DB
# is always enough; wiping the volume is no longer required for schema changes.
COPY db/*.sql /app/schema/
ENV SCHEMA_DIR=/app/schema

RUN chmod +x entrypoint.sh

# Directory where the SQLite file lives — mount a volume here to persist data.
# Only erp.db (generated at runtime) belongs here, never schema files.
VOLUME ["/app/db"]

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
