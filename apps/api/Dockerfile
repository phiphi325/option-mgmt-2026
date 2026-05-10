# Phase 0 placeholder Dockerfile for the FastAPI service.
# Replaced in M0.3 with the real image (uv-based, FastAPI + uvicorn,
# multi-stage build with the engine package mounted).
#
# This stub exists so `docker compose build api` does not fail in M0.1.
FROM python:3.12-slim
WORKDIR /code
RUN echo "FastAPI shell arrives in M0.3 — see plan §17 / §19 day 3" > /tmp/M0.1_PLACEHOLDER
CMD ["python", "-c", "import time; print('apps/api: M0.1 placeholder; replaced in M0.3'); time.sleep(86400)"]
