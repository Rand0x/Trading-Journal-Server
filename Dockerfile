# Multi-architecture Dockerfile for the Trading Journal Server
# Compatible with linux/arm/v7 (32-bit), linux/arm64 (64-bit), and linux/amd64
FROM python:3.12-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_DIR=/app/data \
    PORT=8000

WORKDIR /app

# Install minimal curl for docker healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies with no cache to keep image small
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY server /app/server

# Create data directory for SQLite database persistence
RUN mkdir -p /app/data

# Run as non-privileged user for security
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app

USER trader

# Expose port
EXPOSE 8000

# Docker healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Start Uvicorn with one worker; scale with a reverse proxy if needed.
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "50", "--backlog", "128"]
