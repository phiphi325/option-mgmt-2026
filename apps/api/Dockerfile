# Multi-stage Dockerfile for the FastAPI service.
#
# Stage 1 (builder): uses the official Astral uv image to install Python deps
# into a venv at /code/.venv. Build cache is mounted on /root/.cache/uv so
# repeated builds are fast.
#
# Stage 2 (runtime): python:3.12-slim + libpq5 (for psycopg) + curl (for the
# Docker HEALTHCHECK). Inherits the venv from the builder stage.
#
# Build context: ./apps/api  (set by docker-compose.yml `build: ./apps/api`)
#
# Replaces the M0.1 placeholder Dockerfile.

# ---- builder ----------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/code/.venv

WORKDIR /code

# Install dependencies first to maximise docker-layer cache reuse.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Copy app code + alembic config.
COPY app ./app
COPY alembic.ini ./

# ---- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY --from=builder /code/.venv /code/.venv
COPY --from=builder /code/app /code/app
COPY --from=builder /code/alembic.ini /code/alembic.ini

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/code

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
