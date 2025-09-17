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

# Default environment configuration (override at runtime)
ENV API_HOST=0.0.0.0 \
	API_PORT=8000 \
	LOG_LEVEL=INFO

# Expose FastAPI port
EXPOSE 8000

# Health check hitting the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:8000/health || exit 1

# Start application (allows server.py to manage uvicorn invocation / env)
CMD ["python", "server.py"]