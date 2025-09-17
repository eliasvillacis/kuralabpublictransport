## Dockerfile for Vaya (Public Transport Assistant)
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install minimal system utilities (curl for health checks / debugging)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source
COPY . .

# Create non-root user for security
RUN useradd -m -u 1001 appuser \
	&& chown -R appuser:appuser /app
USER appuser

# Default environment configuration (override at runtime)
ENV API_HOST=0.0.0.0 \
	API_PORT=8000 \
	LOG_LEVEL=INFO

# Expose FastAPI port
EXPOSE 8000

# Health check hitting the /health endpoint (use PORT if provided by platform like Render)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
	CMD curl --fail http://localhost:${PORT:-8000}/health || exit 1

# Start application with uvicorn directly for better prod behavior
ENV UVICORN_WORKERS=1
# Use shell form so that env vars expand at runtime; bind to platform PORT if present (Render sets PORT)
CMD python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-1}