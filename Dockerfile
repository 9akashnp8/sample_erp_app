# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app

COPY ./certs/cpc-ca01.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY db/ ./db/
COPY scripts/ ./scripts/
COPY erp_client.py .
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh

# Directory where the SQLite file lives — mount a volume here to persist data
VOLUME ["/app/db"]

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
