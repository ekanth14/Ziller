# =============================================================================
# ZILLERS Production Docker Container
# Multi-stage, non-root user, SQLite WAL-optimized, fail-closed security
# =============================================================================

FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root unprivileged service account
RUN useradd -m -u 10001 zillers

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY --chown=zillers:zillers cryptoscope ./cryptoscope
COPY --chown=zillers:zillers .env.example ./
COPY --chown=zillers:zillers pytest.ini ./

# Create data directories with appropriate permissions
RUN mkdir -p /app/work/runtime /app/data && chown -R zillers:zillers /app/work /app/data

USER zillers

ENV HOST=0.0.0.0
ENV PORT=8900
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8900

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8900/health || exit 1

ENTRYPOINT ["python", "-m", "cryptoscope.dashboard", "--port", "8900"]
