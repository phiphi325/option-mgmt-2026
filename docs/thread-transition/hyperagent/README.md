# Hyperagent Thread Export — M1.16a: POST /engine/collar-builder

**Thread closed:** 2026-05-13  
**Repo:** csupenn/option-mgmt-2026  
**Summary:** Shipped M1.16a — `POST /engine/collar-builder` API endpoint (PR #60, squash SHA `9c63a15`). Followed by post-merge documentation: README milestone table update, thread transition doc, and handoff memory.

---

## Contents

| File | What |
|---|---|
| [`memories/memories.md`](memories/memories.md) | One handoff memory created (category: `active_work`) |
| [`working-doc.md`](working-doc.md) | Full snapshot of the thread context doc |

**No skills, named agents, or library artifacts** were created in this thread.

---

## Thread snapshot

| | |
|---|---|
| **Engine version** | `1.5.0` (unchanged — M1.16a is API-only) |
| **Test count** | ~830 → ~840 (+9 API tests in `apps/api/tests/`) |
| **API endpoints** | 17 → 18 (added `POST /engine/collar-builder`) |
| **Commits merged to main** | `9c63a15` (M1.16a feature), `c90444f` (docs / README / transition doc) |
| **Next milestone** | M1.11b — wire Collar Builder into `produce_daily_decision()` (engine `1.6.0`) |

## Files touched in M1.16a (PR #60)

| File | Change |
|---|---|
| `apps/api/app/services/collar_builder_service.py` | **New** — thin service layer; owns all DB reads (chain, positions, iv_history, market_state, flow_score, profile) |
| `apps/api/app/schemas/engine.py` | **Modified** — added `CollarBuilderRequest`, `CollarLegResponse`, `CollarStructureResponse` |
| `apps/api/app/routers/engine.py` | **Modified** — added `POST /collar-builder` route; `ValueError` → HTTP 422 |
| `apps/api/tests/test_engine_collar_builder.py` | **New** — 9 tests: auth (401), happy-path ×6, errors ×2 |

## Post-merge docs (commit `c90444f`)

| File | Change |
|---|---|
| `README.md` | Added M1.16a milestone row; updated Status + "Where we are" (17 → 18 endpoints) |
| `docs/thread-transitions/2026-05-13-t02-m1.16a-collar-builder-endpoint.md` | New thread transition record |
