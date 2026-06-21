FROM python:3.12-slim AS base

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ──────────────────────────────────────────────────────────────
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[ui]" 2>/dev/null || pip install --no-cache-dir \
    fastapi>=0.115.0 \
    "uvicorn[standard]>=0.32.0" \
    "passlib[bcrypt]>=1.7.4" \
    "python-jose[cryptography]>=3.3.0" \
    litellm>=1.50.0 \
    slowapi>=0.1.9 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.0

COPY src/ ./src/
COPY config/ ./config/
COPY ui/backend/ ./ui/backend/

# ── Frontend build ────────────────────────────────────────────────────────────
COPY ui/frontend/ ./ui/frontend/
RUN cd ui/frontend && npm ci && npm run build

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8080

CMD ["uvicorn", "ui.backend.app:app", "--host", "0.0.0.0", "--port", "8080"]
