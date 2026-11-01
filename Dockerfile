FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and project files
COPY requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt || true

COPY . /app/

# Create runtime directories and set non-root user
RUN mkdir -p /app/data && \
    useradd -u 1001 -m zillers && \
    chown -R zillers:zillers /app

USER zillers

EXPOSE 8900

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8900/health || exit 1

CMD ["python", "-m", "cryptoscope.dashboard", "--host", "0.0.0.0", "--port", "8900"]
