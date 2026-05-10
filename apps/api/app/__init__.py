"""option-mgmt-api — FastAPI service for the MSFT Option Risk Management Engine.

Wired across milestones:
  M0.2 — db/ package + Alembic migrations (this PR).
  M0.3 — main.py with /healthz + /version + JWT scaffolding.
  M0.4–M0.6 — TS type generation + CI.
  M1.x — engine routers (/engine/*), data routers (/data/*), profile, outcomes.
"""
