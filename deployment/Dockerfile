# Multi-stage Dockerfile for E-commerce Churn Prediction API - Production Ready
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Development
FROM python:3.11-slim as development

WORKDIR /app
ENV ENVIRONMENT=development \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY . .
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.inference.api_server:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 3: Production - Minimal, secure image
FROM python:3.11-slim as production

WORKDIR /app
ENV ENVIRONMENT=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY config/ ./config/
COPY src/ ./src/
COPY artifacts/ ./artifacts/
COPY .env.example ./.env

# Security: non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Logging directory
RUN mkdir -p /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run with Gunicorn + Uvicorn workers for production
RUN pip install --user --no-cache-dir gunicorn==21.2.0

CMD ["gunicorn", \
     "src.inference.api_server:app", \
     "--workers=4", \
     "--worker-class=uvicorn.workers.UvicornWorker", \
     "--bind=0.0.0.0:8000", \
     "--timeout=120", \
     "--graceful-timeout=60", \
     "--keep-alive=5", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "--log-level=info"]

# Build: docker build -t churn-prediction-api:latest --target production .
#
# Run command:
# docker run -p 8000:8000 \
#   -e ENVIRONMENT=prod \
#   -e REDIS_HOST=redis-server \
#   -e AWS_ACCESS_KEY_ID=xxx \
#   -e AWS_SECRET_ACCESS_KEY=xxx \
#   churn-api:latest
