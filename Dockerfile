# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Trust the corporate proxy's CA so pip can reach PyPI through TLS inspection.
COPY certs/cpc-ca01.crt /usr/local/share/ca-certificates/cpc-ca01.crt
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Install dependencies first for better layer caching
COPY requirements.txt .
# The corporate proxy's TLS chain includes a weak (sub-2048-bit) key that
# OpenSSL 3.x rejects outright regardless of CA trust, and the network team
# has confirmed it can't be strengthened — so we skip verification for pip's
# own hosts specifically rather than weakening TLS for the whole image.
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org \
    -r requirements.txt

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
