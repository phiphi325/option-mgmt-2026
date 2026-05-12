# Tutorial: API Reference (`/api/v1/*`)

> **Audience.** Full-stack engineers integrating against the API; first-year master's students who have read the engine-layer tutorials and now want to see how those modules are exposed; reviewers of the M1.14–M1.17.5 pull requests.
> **Prerequisites.** Read at least the [Master Decision Engine](./master-decision-engine.md) tutorial first. Familiarity with the upstream engine tutorials ([Market State](./market-state-engine.md), [Flow Score](./flow-score-engine.md), [Confidence Composer](./confidence-composer.md), [Scoring Primitives](./scoring-primitives.md)) is recommended but not strictly required for the API surface alone.
> **Reading time.** ~50 min careful read with the exercises; ~20 min skim.
> **Coverage.** All seventeen public endpoints shipped through M1.17.5 — the seven `/engine/*` routes (M1.14–M1.16), the four `/data/*/import-csv` routes (M1.17), the three `/profile` + `/outcomes` routes (M1.17), `/market/{ticker}/latest` (M1.17), `/health` + `/healthz` + `/version` (M0.3), plus the M1.17.5 optional-inputs hydration path on `/engine/daily-plan`. Engine version `1.4.0`; API version stamped on `/version`.
>
> **Scope note.** Earlier revisions of this tutorial were titled "Engine API Reference" and covered only `/api/v1/engine/*`. M1.17 + M1.17.5 added enough adjacent surface area (data import, profile, outcomes, market read-through, optional-inputs hydration) that splitting the doc would force readers to chase three files for a workflow that spans one. Title broadened, file path kept for backward-compatible links.
>
> **Disclaimer.** This tutorial is **educational material**. The endpoints documented here are decision-support; they do not place trades, do not check broker margin, and do not constitute investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why a separate API tutorial?](#1-why-a-separate-api-tutorial)
2. [The endpoints at a glance](#2-the-endpoints-at-a-glance)
3. [Authentication](#3-authentication)
4. [Error envelope (RFC 7807)](#4-error-envelope-rfc-7807)
5. [`POST /engine/daily-plan` — the primary endpoint (M1.14, optional-inputs M1.17.5)](#5-post-enginedaily-plan--the-primary-endpoint-m114-optional-inputs-m1175)
6. [`POST /engine/recommend` — rule pipeline only (M1.14)](#6-post-enginerecommend--rule-pipeline-only-m114)
7. [`POST /engine/what-if` — transient evaluation (M1.15)](#7-post-enginewhat-if--transient-evaluation-m115)
8. [The four sub-step endpoints (M1.15 + M1.16)](#8-the-four-sub-step-endpoints-m115--m116)
9. [Idempotency, replay, and the three-pin lock](#9-idempotency-replay-and-the-three-pin-lock)
10. [The V1 hydration story](#10-the-v1-hydration-story)
11. [End-to-end worked example](#11-end-to-end-worked-example)
12. [`/profile` — user strategy profile (M1.17)](#12-profile--user-strategy-profile-m117)
13. [`/outcomes` — manual outcome tracking (M1.17)](#13-outcomes--manual-outcome-tracking-m117)
14. [`/data/*/import-csv` — five CSV upload endpoints (M1.17)](#14-dataimport-csv--five-csv-upload-endpoints-m117)
15. [`GET /market/{ticker}/latest` — convenience read-through (M1.17)](#15-get-marketticker-latest--convenience-read-through-m117)
16. [The M1.17.5 hydration path — how `inputs` becomes optional](#16-the-m1175-hydration-path--how-inputs-becomes-optional)
17. [Plan deviations](#17-plan-deviations)
18. [Hands-on exercises](#18-hands-on-exercises)
19. [Further reading](#19-further-reading)
20. [Glossary](#20-glossary)

---

## 1. Why a separate API tutorial?

The five existing engine-layer tutorials teach you *how the engine thinks*. They cover regime classification, the V1 Flow Score contract, multiplicative confidence composition, deterministic decision orchestration. They are deep, math-heavy, and target a learner.

This tutorial answers a different question: **once the engine exists, how do you actually call it from Python, TypeScript, or curl?** It is shorter (~35 min vs. 50–75 for the engine tutorials), it quotes JSON request/response bodies instead of math, and it targets a developer integrating the API rather than a learner trying to understand the model.

The two doc styles are complementary:

- An engine tutorial answers *"why does HIGH_IV_PIN emit `SELL_COVERED_CALL_PARTIAL`?"*
- This tutorial answers *"what HTTP request gets me that decision, and how does the response shape its actionable fields?"*

Both matter. Engineers writing the Today-screen client need this tutorial. Engineers extending the engine need the others.

### 1.1 What "engine API" means here

Per master plan §7 + ADR-0001, the engine ships as a pure-function Python package and is wrapped in a FastAPI service. Every endpoint in this tutorial lives under `/api/v1/engine/*` and follows the same recipe:

```
HTTP request → Pydantic shell validates → service-layer wrapper → engine pure function → JSON projection
```

Pure-function discipline (ADR-0005) means the engine layer never touches the DB, the wall clock, or the network. The service layer owns all of that. This tutorial is mostly about the service layer; the engine tutorials cover what happens inside the pure functions.

### 1.2 What this tutorial is NOT

- It is not a complete OpenAPI spec (the live `/api/v1/openapi.json` is).
- It does not document `/auth/*`, `/health`, `/healthz`, `/version`, `/profile`, `/outcomes`, or `/data/*` — only `/engine/*`.
- It does not cover M1.16a (`/engine/collar-builder`) — that endpoint depends on the M1.11a Collar Builder engine module, which has not yet shipped on `main` (see [`docs/phased-design/phase-1/m1.0-m1.14-shipped-summary.md`](../phased-design/phase-1/m1.0-m1.14-shipped-summary.md) for status).

---

## 2. The endpoints at a glance

### Engine endpoints (M1.14 – M1.16)

| Endpoint | Milestone | Wraps | Persists? | Auth |
|---|---|---|---|---|
| `POST /engine/daily-plan` | M1.14 / M1.17.5 | `engine.produce_daily_decision()` | Yes (idempotent via `ON CONFLICT`) | Required |
| `POST /engine/recommend` | M1.14 | `engine.recommend()` | No | Required |
| `POST /engine/what-if` | M1.15 | `engine.produce_daily_decision()` | **Never** (§22.14) | Required |
| `POST /engine/market-state` | M1.15 | `engine.market_state.classify()` | No | Required |
| `POST /engine/flow-score` | M1.15 | `engine.flow_score.compute()` | No | Required |
| `POST /engine/strike-candidates` | M1.16 | `engine.strike_selector.select_strikes()` | No | Required |
| `POST /engine/execution-check` | M1.16 | `engine.execution.assess()` | No | Required |

`POST /engine/collar-builder` (M1.16a, master plan v1.1) is still pending — blocked on the M1.11a Collar Builder engine module, which hasn't shipped to `main` yet. Once it lands, all of §7 will be HTTP-reachable.

### Data + profile + outcomes endpoints (M1.17)

| Endpoint | Wraps | Persists? | Auth |
|---|---|---|---|
| `GET /profile` | `users.strategy_profile` JSONB | n/a (read) | Required |
| `PUT /profile` | `users.strategy_profile` JSONB | Yes (full replace) | Required |
| `GET /outcomes?since=&limit=&cursor=` | `outcomes` (cursor-paginated) | n/a (read) | Required |
| `POST /outcomes` | `outcomes` INSERT | Yes (409 on duplicate `daily_decision_id`) | Required |
| `PATCH /outcomes/{outcome_id}` | `outcomes` partial UPDATE | Yes | Required |
| `POST /data/positions/import-csv` | `positions` UPSERT | Yes (idempotent on `(user_id, ticker, opened_at)`) | Required |
| `POST /data/option-positions/import-csv` | `option_positions` UPSERT | Yes (idempotent on 7-tuple) | Required |
| `POST /data/chain/import-csv` | `option_chain_snapshots` APPEND | Yes (dedupes on exact match) | Required |
| `POST /data/iv/import-csv` | `iv_history` UPSERT | Yes; rejects (§22.12) if final count < 30 rows | Required |
| `POST /data/events/import-csv` | `events` INSERT | Yes (dedupes on `(ticker, kind, scheduled_at, source)`) | Required |
| `GET /market/{ticker}/latest` | DB read-through (§22.10) | No | Public (no auth) |

### System endpoints (M0.3)

| Endpoint | Returns | Auth |
|---|---|---|
| `GET /health` | `{status, uptime_seconds, db, version, engine_version, weights_version}` | Public |
| `GET /healthz` | Alias of `/health` (k8s convention) | Public |
| `GET /version` | `{version, engine_version, weights_version, git_sha}` | Public |

### 2.1 Mental model — five categories

The endpoints fall into five categories. The first three are the engine surface; the last two are the data + system surface.

```
┌─────────────────────────────────────────────────────────┐
│  PRIMARY (engine; persists)                             │
│    /engine/daily-plan      ← user's daily ritual        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TRANSIENT (engine call; never persisted)               │
│    /engine/what-if         ← "what if spot were 425?"   │
│    /engine/recommend       ← rule-pipeline-only         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  DRILL-DOWN (single engine module; never persisted)     │
│    /engine/market-state    ← classify() only            │
│    /engine/flow-score      ← compute() only             │
│    /engine/strike-candidates ← select_strikes() only    │
│    /engine/execution-check ← assess() only              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  DATA (CRUD on user-owned + ingested rows)              │
│    /profile                ← strategy preferences       │
│    /outcomes               ← manual outcome tracking    │
│    /data/*/import-csv      ← 5 CSV upload endpoints     │
│    /market/{ticker}/latest ← convenience read-through   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SYSTEM (operational; no auth)                          │
│    /health, /healthz, /version                          │
└─────────────────────────────────────────────────────────┘
```

The PRIMARY + TRANSIENT + DRILL-DOWN categories are documented in §§5–8 below. The DATA category is documented in §§12–15. The SYSTEM category is intentionally brief — `/health` and `/version` return the obvious shape and are skipped in this tutorial.

Today-screen UI calls **primary** on the user's daily visit. Today-screen drill-down panels (under "Why" / "Risks" / "Invalidation") call the **drill-down** group to show the user what each engine sub-step contributed. The **transient** group is for backtesting, scenario play, and the Phase 4 ML calibration harness.

---

## 3. Authentication

Every `/engine/*` endpoint requires a JWT bearer token. JWTs are minted by `POST /api/v1/auth/login` (returns `{ access_token, token_type }`).

```bash
$ curl -X POST https://api.example.com/api/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email": "user@example.com", "password": "..."}'

{"access_token": "eyJhbGciOi...","token_type": "bearer"}
```

Subsequent calls send the token in the `Authorization` header:

```bash
$ curl -X POST https://api.example.com/api/v1/engine/daily-plan \
    -H 'Authorization: Bearer eyJhbGciOi...' \
    -H 'Content-Type: application/json' \
    -d @body.json
```

### 3.1 Failure modes

| Header state | Status | Body title |
|---|---|---|
| Missing `Authorization` header | `401` | `"Not authenticated"` |
| Malformed token (not `Bearer xxx`) | `401` | `"Could not validate credentials"` |
| Token signature mismatch (wrong `JWT_SECRET`) | `401` | `"Could not validate credentials"` |
| Token expired (past `exp` claim) | `401` | `"Could not validate credentials"` |

The 401 body follows the RFC 7807 envelope (see §4).

### 3.2 What `user_id` does (and doesn't do)

The JWT's `sub` claim is parsed into `user_id`. Most engine endpoints accept it for **future** rate-limiting and audit purposes but don't currently scope behavior to the user — the actual scoping happens at the persistence layer (`daily_decisions.user_id` FK).

The single endpoint where `user_id` materially changes behavior is `POST /engine/daily-plan`: persistence writes the row against the authenticated user. Two different users posting the same `inputs` produce two different `daily_decisions` rows (different `(user_id, inputs_hash)` keys). A single user posting the same `inputs` twice gets one row, returned twice — see §9.

---

## 4. Error envelope (RFC 7807)

All non-2xx responses use [RFC 7807](https://tools.ietf.org/html/rfc7807) Problem Details:

```json
{
  "type": "about:blank",
  "title": "Could not validate credentials",
  "status": 401,
  "detail": null,
  "instance": "/api/v1/engine/daily-plan"
}
```

| Field | Meaning |
|---|---|
| `type` | URI identifying the error class. `"about:blank"` for generic HTTP errors. |
| `title` | Short human-readable summary. |
| `status` | HTTP status code (echoed for convenience). |
| `detail` | Long-form explanation. Null when `title` is self-explanatory. |
| `instance` | The request path that produced the error (helps with log correlation). |

### 4.1 Status code conventions

| Status | When |
|---|---|
| `200` | Success. The body matches the endpoint's documented response schema. |
| `401` | Auth failure (see §3.1). |
| `422` | Request body fails Pydantic validation OR the engine raises `ValueError`. The `title` describes which. |
| `500` | Unhandled exception. Indicates a bug — please file. |

In dev mode (`is_dev=True`), 500s include the raw exception message in `detail`. In production they omit it.

### 4.2 Pydantic 422 example

Posting `{"inputs": {...}, "market_state": {"iv_rank": 1.5, ...}}` to `/daily-plan` violates the `iv_rank ≤ 1.0` constraint:

```json
{
  "type": "about:blank",
  "title": "Validation error",
  "status": 422,
  "detail": "1 validation error for DailyPlanRequest\ninputs.market_state.iv_rank\n  Input should be less than or equal to 1.0 ...",
  "instance": "/api/v1/engine/daily-plan"
}
```

The detail string is FastAPI's auto-generated message. Clients should parse it heuristically rather than depend on its exact format.

---

## 5. `POST /engine/daily-plan` — the primary endpoint (M1.14, optional-inputs M1.17.5)

The headline endpoint. Runs the full Master Decision Engine and (by default) persists a `daily_decisions` row.

As of M1.17.5, **`inputs` is OPTIONAL**. When omitted, the API service hydrates `EngineInputs` from the latest DB rows (positions / option_chain_snapshots / iv_history / hv_history / events / users.strategy_profile) and reproduces the upstream engine pipeline (`market_state.classify` + `flow_score.compute`) server-side. Full hydration semantics live in §16.

### 5.1 Request (two shapes)

**Shape A — fully hydrated (M1.14 path, still supported):**

```json
{
  "ticker": "MSFT",
  "as_of": "2026-05-20T14:30:00Z",
  "inputs": {
    "chain_snapshot": { /* ChainSnapshot — engine.types */ },
    "positions": { /* PositionState — engine.recommendation */ },
    "profile": { /* UserStrategyProfile — engine.profiles */ },
    "market_state": { /* MarketStateResult — engine.market_state */ },
    "flow_score": { /* FlowScore — engine.flow_score */ }
  },
  "persist": true
}
```

**Shape B — DB-hydrated (M1.17.5, recommended for live use):**

```json
{
  "ticker": "MSFT",
  "as_of": "2026-05-20T14:30:00Z",
  "persist": true
}
```

When `inputs` is omitted, the service hydrates from DB. The 422 cases for missing prerequisites are documented in §16.

| Field | Type | Default | Notes |
|---|---|---|---|
| `ticker` | `str` (1–10 chars) | `"MSFT"` | MSFT-only in V1; reserved for multi-ticker post-M4.11. |
| `as_of` | ISO 8601 datetime | server `now(UTC)` | Decision timestamp. Pinned for replay. |
| `inputs` | `EngineInputs | null` | **optional as of M1.17.5** | Full hydrated bundle. When `null` or omitted, the service hydrates from DB (§16). |
| `inputs.chain_snapshot` | `ChainSnapshot` | required | Frozen option chain with `spot`, `as_of`, `contracts: tuple[OptionContract, ...]`. |
| `inputs.positions` | `PositionStateModel` | required | User's current MSFT shares + option positions. |
| `inputs.profile` | `UserStrategyProfile` | required | Risk tolerance, coverage cap, delta band, DTE band, etc. |
| `inputs.market_state` | `MarketStateResultModel` | required | Pre-computed regime + 18 §22.3 inputs. |
| `inputs.flow_score` | `FlowScoreModel` | required | Pre-computed V1 contract (§22.2). |
| `persist` | `bool` | `true` | Set to `false` for a transient run. Use `/engine/what-if` for the canonical non-persisting path. |

### 5.2 Response

```json
{
  "decision": {
    "decision_id": "dd_a1b2c3d4e5f6_1748530200",
    "as_of": "2026-05-20T14:30:00Z",
    "ticker": "MSFT",
    "spot": 415.0,
    "user_profile_snapshot": { /* echoed UserStrategyProfile */ },
    "market_state": { /* full MarketStateResult */ },
    "flow_score": { /* full FlowScore */ },
    "recommendation": {
      "regime": "HIGH_IV_PIN",
      "matched_rule": { /* RuleSpec + rendered rationale */ },
      "actions": [
        {
          "emit": "SELL_COVERED_CALL_PARTIAL",
          "parameters": {
            "target_delta": 0.25,
            "target_dte": 30.0,
            "size_pct": 0.5
          }
        }
      ],
      "confidence": 0.62,
      "confidence_breakdown": { /* ConfidenceBreakdown */ },
      "rationale": "...",
      "risks": ["..."],
      "invalidation": ["..."]
    },
    "strike_selections": [ /* one StrikeSelection per Action */ ],
    "downgrades": [ /* DowngradeResult per leg */ ],
    "executions": [ /* Execution per Action */ ],
    "confidence": 0.62,
    "confidence_breakdown": { /* same as recommendation.confidence_breakdown */ },
    "inputs_hash": "sha256:abc123...",
    "engine_version": "1.4.0",
    "weights_version": "v2.0",
    "data_freshness": { /* per-input age stamps */ },
    "disclaimers": ["..."],
    "escalated": false
  },
  "is_new_row": true
}
```

The `decision` payload is the full `DailyDecision` dataclass, recursively serialized to JSON via the helper documented in the [Master Decision Engine tutorial §6](./master-decision-engine.md). The `is_new_row` flag is the persistence-layer discriminant:

- `true` — a fresh row was inserted into `daily_decisions`.
- `false` — `ON CONFLICT (user_id, inputs_hash) DO NOTHING` fired; an existing row with identical inputs is referenced. The response body still echoes the decision; nothing was double-persisted.

This guarantees safe client retries: posting the same body twice produces two HTTP 200s with byte-equivalent `decision` payloads and exactly one DB row. See §9.

### 5.3 curl example

```bash
$ curl -X POST $API/engine/daily-plan \
    -H "Authorization: Bearer $JWT" \
    -H "Content-Type: application/json" \
    -d @daily_plan_body.json | jq '.decision.recommendation.actions[0]'

{
  "emit": "SELL_COVERED_CALL_PARTIAL",
  "parameters": {
    "target_delta": 0.25,
    "target_dte": 30.0,
    "size_pct": 0.5
  }
}
```

A complete request body fixture lives at [`apps/api/tests/test_smoke_engine.py`](../../apps/api/tests/test_smoke_engine.py) → `_inputs_payload()`.

---

## 6. `POST /engine/recommend` — rule pipeline only (M1.14)

Runs the M1.9 rule pipeline against `(MarketStateResult, FlowScore, PositionState, UserStrategyProfile)` and returns the `RecommendationResult` — the matched rule, the emitted actions, the M1.10 confidence breakdown — **without** going through strike selection, execution feasibility, downgrade, or two-stage composition. No persistence.

### 6.1 When to use it

- UI drill-down: "what would the rule engine say without execution feedback?"
- Debugging: isolate rule-matching from downstream noise (slippage, liquidity).
- Backtest harness for `rules.yaml` changes.

### 6.2 Request / response

```json
{
  "ticker": "MSFT",
  "market_state": { /* full MarketStateResult */ },
  "flow_score":   { /* full FlowScore */ },
  "positions":    { /* PositionState */ },
  "profile":      { /* UserStrategyProfile */ }
}
```

The response carries `recommendation: dict` only (no `decision_id`, no `inputs_hash`, no execution feasibility — those belong to `/daily-plan`):

```json
{
  "recommendation": {
    "regime": "HIGH_IV_PIN",
    "matched_rule": { /* ... */ },
    "actions": [ /* ... */ ],
    "confidence": 0.62,
    "confidence_breakdown": { /* illiquidity_penalty=0 — execution skipped */ },
    "rationale": "...",
    "risks": [...],
    "invalidation": [...]
  }
}
```

Note `illiquidity_penalty = 0` in the breakdown: `/recommend` skips the M1.11 execution module by design, so the composer runs the "pre-execution" view.

---

## 7. `POST /engine/what-if` — transient evaluation (M1.15)

Same engine pipeline as `/daily-plan`, but with two key differences:

1. **It never persists.** Per master plan §22.14, what-if is explicitly transient. The response carries `is_new_row: false` as a permanent discriminant so client code that handles `DailyDecisionResponse` can also handle this shape.
2. **It accepts an `overrides` dict.** Flat fields on `inputs.market_state` can be overridden before the engine runs, matching the canonical example in §7 of the master plan (`{"spot": 425.0, "iv_rank": 0.35}`).

### 7.1 Override semantics

```json
{
  "ticker": "MSFT",
  "as_of": "2026-05-20T14:30:00Z",
  "inputs": { /* same as DailyPlanRequest.inputs */ },
  "overrides": {
    "iv_rank": 0.35,
    "spot": 425.0
  }
}
```

The keys in `overrides` must match `MarketStateResultModel.model_fields` (validated against a 23-key allowlist). Unknown keys raise 422 immediately with the offending keys listed:

```json
{
  "type": "about:blank",
  "title": "unsupported override keys (must match MarketStateResultModel fields): ['not_a_real_field']",
  "status": 422,
  "instance": "/api/v1/engine/what-if"
}
```

After key validation, the merged `market_state` is re-validated through the Pydantic model so out-of-range overrides (e.g. `{"iv_rank": 1.5}`) also surface as 422 rather than crashing inside the engine.

To override fields on `chain_snapshot`, `positions`, `profile`, or `flow_score`, post a modified `inputs` bundle. The `overrides` shortcut is intentionally scoped to `market_state` for V1 — that's where the §7-canonical knobs (`spot`, `iv_rank`, `regime`) live.

### 7.2 Non-persistence contract — what to verify

The strongest test of §22.14 is the smoke fixture: `tests/test_smoke_engine.py::test_what_if_does_not_persist_smoke` runs `/what-if` twice against a live Postgres and asserts `SELECT COUNT(*) FROM daily_decisions WHERE user_id = ?` is unchanged before vs. after. Client implementations can rely on this contract — the response's `inputs_hash` is computed (the engine produces one) but no row is ever written.

### 7.3 Sample use

```bash
# Baseline: what would the engine recommend right now?
$ curl -X POST $API/engine/what-if \
    -H "Authorization: Bearer $JWT" \
    -d '{"inputs": {...}, "overrides": {}}' | jq '.decision.recommendation.actions[0].emit'
"SELL_COVERED_CALL_PARTIAL"

# Scenario: what if IV collapsed to rank 0.20?
$ curl -X POST $API/engine/what-if \
    -H "Authorization: Bearer $JWT" \
    -d '{"inputs": {...}, "overrides": {"iv_rank": 0.20}}' | jq '.decision.recommendation.actions[0].emit'
"BUY_LONG_DATED_PUT"
```

---

## 8. The four sub-step endpoints (M1.15 + M1.16)

These four endpoints expose a single engine module each. They share a uniform shape:

```
POST /api/v1/engine/<sub-step>
  ↓
Pydantic shell validates the inputs the engine module needs
  ↓
service wrapper calls the engine pure function (no DB, no clock)
  ↓
response is the engine result's JSON projection
```

### 8.1 `POST /engine/market-state` (M1.15)

Runs only `engine.market_state.classify()` per §9.2 + §22.3. The request body is flat: all 18 inputs to `classify()` are top-level keys, not wrapped in any sub-structure.

```json
{
  "ticker": "MSFT",
  "spot": 415.0,
  "iv_rank": 0.65,
  "iv_percentile": 0.60,
  "hv_30": 0.22,
  "expected_move_pct": 0.04,
  "max_pain": 415.0,
  "pcr_volume": 0.50,
  "pcr_oi": 0.50,
  "trend_strength": 0.30,
  "realized_vs_implied": 1.0,
  "breakout_signal": 0.0,
  "oi_concentration_at_max_pain": 0.30,
  "days_to_next_event": 14,
  "next_event_kind": "earnings",
  "days_since_event": null,
  "days_to_nearest_opex": 2,
  "iv_rank_change_1d": 0.0,
  "gap_pct": null
}
```

Response:

```json
{
  "market_state": {
    "regime": "HIGH_IV_PIN",
    "regime_score": 0.78,
    "all_scores": {
      "HIGH_IV_EVENT": 0.42,
      "HIGH_IV_PIN": 0.78,
      "LOW_IV_TREND": 0.12,
      "LOW_IV_RANGE": 0.18,
      "BREAKOUT": 0.05,
      "POST_EVENT_REPRICE": 0.10
    },
    "tags": ["sell_vol_favorable", "pin_likely"],
    /* … 18 inputs echoed for explainability … */
  }
}
```

The 18-input echo is intentional: it lets the UI show the user *which* inputs drove the regime selection. The `all_scores` map enables tie-break visualization ("HIGH_IV_PIN edged out HIGH_IV_EVENT by 0.36").

### 8.2 `POST /engine/flow-score` (M1.15)

Runs only `engine.flow_score.compute()` per §9.3a. The body is sparse — just the chain snapshot plus a few scalars:

```json
{
  "ticker": "MSFT",
  "chain_snapshot": { /* ChainSnapshot */ },
  "spot": 415.0,
  "expiry_focus": ["2026-06-19"],
  "dte_to_nearest_opex": 30,
  "risk_free_rate": 0.05,
  "dividend_yield": 0.0
}
```

Note `compute()` does NOT take a `UserStrategyProfile` — the V1 `recommended_action` decision tree depends only on `score / gamma_risk / pin_probability`. This deviates from an earlier draft of the M1.15 dev spec; the engine wins (§9.3a is the source of truth).

Response carries the full V1 LOCKED contract:

```json
{
  "flow_score": {
    "score": 35.0,
    "bullish_score": 55.0,
    "bearish_score": 20.0,
    "bias": "NEUTRAL_BULLISH",
    "recommended_action": "SELL_CALL_PARTIAL",
    "pin_probability": 0.42,
    "gamma_risk": 0.18,
    "gamma_sign": 0,
    "confidence": 0.70,
    "explanation": "Resistance OI wall at 420 ...",
    "breakdown": { /* 13 component scores */ }
  }
}
```

### 8.3 `POST /engine/strike-candidates` (M1.16)

Runs only `engine.strike_selector.select_strikes()` per §9.4. Takes an `Action` (from a prior `/recommend` or `/daily-plan` call) + a `ChainSnapshot`:

```json
{
  "ticker": "MSFT",
  "action": {
    "emit": "SELL_COVERED_CALL_PARTIAL",
    "parameters": {
      "target_delta": 0.25,
      "target_dte": 30.0,
      "size_pct": 0.5
    }
  },
  "chain_snapshot": { /* ChainSnapshot */ },
  "risk_free_rate": 0.05,
  "dividend_yield": 0.0
}
```

The request takes an `Action`, not a high-level "intent" — this matches the engine's real signature (and is the same shape decision the M1.16 dev spec ended up adopting). The four stable keys in `Action.parameters` are:

- `target_delta` — target absolute BS delta for the new leg
- `target_dte` — target days to expiry
- `size_pct` — fraction of position to act on
- `urgency_days` — rough days-to-act window (advisory only in V1)

Response carries the `StrikeSelection` projection:

```json
{
  "strike_selection": {
    "emit": "SELL_COVERED_CALL_PARTIAL",
    "legs": [
      {
        "contract": {
          "underlying": "MSFT",
          "expiry": "2026-06-19",
          "strike": 420.0,
          "option_type": "CALL",
          "bid": 2.40,
          "ask": 2.50,
          "mid": 2.45,
          "iv": 0.27,
          "open_interest": 2500,
          "volume": 180
        },
        "side": "SHORT",
        "delta_target": 0.25,
        "delta_actual": 0.27,
        "delta_distance": 0.02,
        "dte_actual": 30,
        "mid_price": 2.45
      }
    ],
    "skipped_reason": null
  }
}
```

For zero-leg emits (`NO_OP`, `REDUCE_COVERAGE`, `MONETIZE_PUT`) the response is `legs: []` + a non-null `skipped_reason`:

```json
{
  "strike_selection": {
    "emit": "NO_OP",
    "legs": [],
    "skipped_reason": "NO_OP emit code requires no new legs"
  }
}
```

### 8.4 `POST /engine/execution-check` (M1.16)

Runs only `engine.execution.assess()` per §9.8. Takes a list of `StrikeLeg`s plus optional per-leg `quantities`:

```json
{
  "legs": [
    {
      "contract": { /* OptionContract */ },
      "side": "SHORT",
      "delta_target": 0.25,
      "delta_actual": 0.27,
      "delta_distance": 0.02,
      "dte_actual": 30,
      "mid_price": 2.45
    }
  ],
  "quantities": [5]
}
```

`quantities` defaults to `[1] * len(legs)` when omitted. Length mismatch raises 422 (the engine's defensive check).

Empty `legs` is valid — the response is an aggregate-only `Execution` (no per-leg detail):

```json
{
  "execution": {
    "aggregate_liquidity_score": 1.0,
    "aggregate_fill_confidence": 1.0,
    "suggested_order_type": "limit",
    "legs": [],
    "notes": ["no legs to assess"]
  }
}
```

Happy path with one liquid SHORT call:

```json
{
  "execution": {
    "aggregate_liquidity_score": 0.82,
    "aggregate_fill_confidence": 0.79,
    "suggested_order_type": "limit",
    "legs": [
      {
        "leg_id": "short_call_420_2026-06-19",
        "liquidity_score": 0.82,
        "spread_bps": 41,
        "fill_confidence": 0.79,
        "expected_slippage": 0.025,
        "suggested_order_type": "limit",
        "limit_price_band": [2.43, 2.47],
        "size_warnings": []
      }
    ],
    "notes": []
  }
}
```

When `fill_confidence < 0.50` on any leg, M1.13's full pipeline triggers the M1.12 downgrade ladder. Calling `/execution-check` standalone does NOT trigger downgrade — that's an M1.13 orchestration concern, not an assessment concern.

---

## 9. Idempotency, replay, and the three-pin lock

`POST /engine/daily-plan` is the only endpoint that writes to the DB. Its persistence behavior is locked by three guarantees.

### 9.1 ON CONFLICT idempotency

The persistence SQL is:

```sql
INSERT INTO daily_decisions (
    user_id, ticker, as_of, payload, confidence,
    confidence_breakdown, execution,
    weights_version, engine_version, inputs_hash
)
VALUES (...)
ON CONFLICT (user_id, inputs_hash) DO NOTHING
RETURNING id;
```

The `UNIQUE (user_id, inputs_hash)` constraint is enforced by migration `0002_dd_unique_user_hash.py` (M1.14). The `RETURNING id` returns `NULL` when the conflict fired, which the service layer maps to `is_new_row: false`.

Practical implication: a Today-screen client that retries on network errors never double-persists. The same body posted N times produces 1 row and N identical HTTP 200 responses.

### 9.2 Three-pin replay

Every persisted `DailyDecision` row carries three values that together pin the engine state:

| Column | Source | Meaning |
|---|---|---|
| `engine_version` | `engine.__version__` (currently `1.4.0`) | The package version that produced this decision. |
| `weights_version` | `engine.confidence.weights.yaml`'s declared version (currently `"v2.0"`) | The confidence-composer weight schedule. |
| `inputs_hash` | `engine.decision.compute_inputs_hash(...)` | SHA-256 of the canonical-JSON-serialized engine inputs. |

Given those three values plus a way to retrieve the source inputs (the `payload.market_state.inputs`, `payload.flow_score`, etc. echoed in the persisted row), the decision can be re-derived to byte-equivalence. See the [Master Decision Engine tutorial §8](./master-decision-engine.md) for the canonical-JSON algorithm.

### 9.3 `decision_id` is deterministic

The `decision_id` field on the response is derived from `(inputs_hash, as_of_unix)`:

```
dd_<12-hex-chars-of-inputs_hash>_<as_of_unix>
```

Same inputs + same `as_of` → same `decision_id`. The format is documented at [`packages/engine/engine/decision/`](../../packages/engine/engine/decision/).

---

## 10. The V1 hydration story

In V1 (current `main`), every engine endpoint accepts the full hydrated state in the request body. This is a deliberate simplification:

- **The engine layer never touches the DB.** Pure-function discipline (ADR-0005).
- **The API layer doesn't yet have a `chain_snapshot` source.** M1.17 (`POST /data/chain/import-csv`) is the milestone that lands CSV-import for the chain/iv/hv/events tables. Until M1.17 ships, the only chain data in the system is what the caller puts in the request body.

### 10.1 What changes after M1.17

After M1.17 lands, `DailyPlanRequest.inputs` becomes **optional**:

- If `inputs` is provided, the engine uses it (current behavior).
- If `inputs` is omitted, the service layer hydrates from Postgres: latest `option_chain_snapshots` for the ticker, latest `iv_history` / `hv_history` / `events`, the user's `positions`, the user's `profile`.

This is tracked as the "knock-on commitment" in the M1.17 dev spec at [`docs/phased-design/phase-1/m1.17-profile-outcomes-csv-import.md`](../phased-design/phase-1/m1.17-profile-outcomes-csv-import.md).

The same knock-on applies to `/engine/recommend`, `/engine/what-if`, `/engine/market-state`, `/engine/flow-score`, `/engine/strike-candidates`, `/engine/execution-check` — each gains a thinner body shape once hydration is wired.

### 10.2 Today (pre-M1.17) — synthetic test fixtures

The smoke fixtures at [`apps/api/tests/test_smoke_engine.py`](../../apps/api/tests/test_smoke_engine.py) (`_chain_payload()`, `_market_state_payload()`, etc.) are the canonical example bodies for the V1 endpoints. They are the closest to "production-shaped" data the test suite has today.

---

## 11. End-to-end worked example

This section walks through a complete client flow against a live API. We assume the JWT is in `$JWT` and the API root is `$API` (e.g. `http://localhost:8000/api/v1`).

### 11.1 The scenario

The user is reviewing their MSFT position. Spot is at 415, expected earnings in 14 days, IV elevated, and they want to see:

1. What regime does the engine classify the market in?
2. What does the flow score say?
3. What strategy does the rule pipeline recommend?
4. What concrete strike does the strike selector pick?
5. Will the order actually fill cleanly?

This is the canonical "drill-down" flow. The user could equivalently call `/engine/daily-plan` once and pull all five answers out of the single response, but the standalone endpoints let the UI show progressive disclosure.

### 11.2 Step 1 — Market state classification

```bash
$ curl -X POST $API/engine/market-state \
    -H "Authorization: Bearer $JWT" \
    -H "Content-Type: application/json" \
    -d '{
      "ticker": "MSFT",
      "spot": 415.0,
      "iv_rank": 0.65, "iv_percentile": 0.60, "hv_30": 0.22,
      "expected_move_pct": 0.04,
      "max_pain": 415.0,
      "pcr_volume": 0.50, "pcr_oi": 0.50,
      "trend_strength": 0.30, "realized_vs_implied": 1.0,
      "breakout_signal": 0.0,
      "oi_concentration_at_max_pain": 0.30,
      "days_to_next_event": 14, "next_event_kind": "earnings",
      "days_since_event": null,
      "days_to_nearest_opex": 2,
      "iv_rank_change_1d": 0.0, "gap_pct": null
    }' | jq '.market_state.regime'
"HIGH_IV_PIN"
```

The engine returns `HIGH_IV_PIN`: high implied vol with spot pinned near the max-pain strike close to opex. The UI can render that as a colored badge.

### 11.3 Step 2 — Flow score

```bash
$ curl -X POST $API/engine/flow-score \
    -H "Authorization: Bearer $JWT" \
    -d @flow_score_body.json | jq '.flow_score | {score, bias, recommended_action}'
{
  "score": 35.0,
  "bias": "NEUTRAL_BULLISH",
  "recommended_action": "SELL_CALL_PARTIAL"
}
```

Bullish-leaning flow + the V1 decision tree recommends partial coverage.

### 11.4 Step 3 — Recommendation

```bash
$ curl -X POST $API/engine/recommend \
    -H "Authorization: Bearer $JWT" \
    -d @recommend_body.json | jq '.recommendation.actions[0]'
{
  "emit": "SELL_COVERED_CALL_PARTIAL",
  "parameters": {
    "target_delta": 0.25,
    "target_dte": 30.0,
    "size_pct": 0.5
  }
}
```

The HIGH_IV_PIN + bullish-bias rule fires. The action is to sell a 25-delta covered call at the 30-DTE expiry, half the position.

### 11.5 Step 4 — Strike candidates

```bash
$ curl -X POST $API/engine/strike-candidates \
    -H "Authorization: Bearer $JWT" \
    -d '{
      "ticker": "MSFT",
      "action": {
        "emit": "SELL_COVERED_CALL_PARTIAL",
        "parameters": {
          "target_delta": 0.25, "target_dte": 30.0, "size_pct": 0.5
        }
      },
      "chain_snapshot": { /* loaded from latest chain */ }
    }' | jq '.strike_selection.legs[0] | {strike: .contract.strike, delta_actual, side}'
{
  "strike": 420.0,
  "delta_actual": 0.27,
  "side": "SHORT"
}
```

The selector picks the 420 strike (delta 0.27, close to the 0.25 target).

### 11.6 Step 5 — Execution check

```bash
$ curl -X POST $API/engine/execution-check \
    -H "Authorization: Bearer $JWT" \
    -d '{
      "legs": [
        {
          "contract": { /* the 420 short call */ },
          "side": "SHORT", "delta_target": 0.25, "delta_actual": 0.27,
          "delta_distance": 0.02, "dte_actual": 30, "mid_price": 2.45
        }
      ],
      "quantities": [25]
    }' | jq '.execution | {aggregate_fill_confidence, spread_bps: .legs[0].spread_bps}'
{
  "aggregate_fill_confidence": 0.79,
  "spread_bps": 41
}
```

Fill confidence 0.79 (above the 0.50 downgrade threshold) and a 41-bps spread. Order will likely fill at mid ± half-spread.

### 11.7 Step 6 — Or, one call to rule them all

The same five pieces can come from one `/daily-plan` call:

```bash
$ curl -X POST $API/engine/daily-plan \
    -H "Authorization: Bearer $JWT" \
    -d @daily_plan_body.json | jq '{
      regime: .decision.market_state.regime,
      flow_bias: .decision.flow_score.bias,
      emit: .decision.recommendation.actions[0].emit,
      strike: .decision.strike_selections[0].legs[0].contract.strike,
      fill_confidence: .decision.executions[0].aggregate_fill_confidence,
      decision_id: .decision.decision_id
    }'
{
  "regime": "HIGH_IV_PIN",
  "flow_bias": "NEUTRAL_BULLISH",
  "emit": "SELL_COVERED_CALL_PARTIAL",
  "strike": 420.0,
  "fill_confidence": 0.79,
  "decision_id": "dd_a1b2c3d4e5f6_1748530200"
}
```

Same answers, one round-trip, one persisted row. The drill-down endpoints exist for the UI's progressive-disclosure use case; the primary endpoint exists for the user's daily ritual.

---

## 12. `/profile` — user strategy profile (M1.17)

The user's `UserStrategyProfile` controls how the engine interprets their preferences: which short-premium thresholds apply, what coverage cap to respect, whether collars are preferred over covered calls, and so on. The profile lives in the `users.strategy_profile` JSONB column (created in M0.2) and is hydrated into the engine on every `/engine/daily-plan` call.

### 12.1 `GET /profile`

```bash
$ curl -X GET $API/profile -H "Authorization: Bearer $JWT"
{
  "risk_tolerance": "moderate",
  "income_need": "medium",
  "max_position_pct": 0.50,
  "max_coverage_pct": 0.75,
  "min_iv_rank_for_short_premium": 40,
  "prefer_collars_over_covered_calls": false,
  "drawdown_tolerance": 0.15,
  "style": "balanced"
}
```

Always returns 200. A fresh user with no customizations gets the defaults (moderate / medium / 50% position / 75% coverage / 40 IV-rank threshold / balanced) rather than 404 — the engine needs a profile to function, and defaults are the sensible fallback.

### 12.2 `PUT /profile`

Full replacement (PUT semantics, not PATCH). The request body must contain all fields:

```bash
$ curl -X PUT $API/profile \
    -H "Authorization: Bearer $JWT" \
    -H "Content-Type: application/json" \
    -d '{
      "risk_tolerance": "conservative",
      "income_need": "high",
      "max_position_pct": 0.30,
      "max_coverage_pct": 0.90,
      "min_iv_rank_for_short_premium": 60,
      "prefer_collars_over_covered_calls": true,
      "drawdown_tolerance": 0.08,
      "style": "income"
    }'
```

200 returns the persisted profile (echo of input on success). 422 on Pydantic validation failure — typos and out-of-range values are caught at the API boundary.

### 12.3 The strictness wrinkle — `extra="forbid"` at the API boundary

The engine's `UserStrategyProfile` model deliberately allows unknown fields (forward-compat policy — a future engine can add new fields without breaking existing payloads). The API's `ProfileUpdateRequest` overrides this with `extra="forbid"`. The reason is API UX: a PUT with `max_postion_pct: 0.25` (typo) would silently drop the field if extras were allowed, and the user's intended update would silently fail. Surfacing 422 with the offending key listed is dramatically better.

```bash
$ curl -X PUT $API/profile \
    -H "Authorization: Bearer $JWT" \
    -d '{ /* … */ "max_postion_pct": 0.25 }'
{ "type": "about:blank", "title": "Validation error", "status": 422,
  "detail": "1 validation error for ProfileUpdateRequest\nmax_postion_pct\n  Extra inputs are not permitted ..." }
```

The deviation between API-strict and engine-permissive is documented in `app/schemas/profile.py`.

### 12.4 §9.9 validation rules

Pydantic enforces all §9.9 numeric ranges + enum membership at request parse time:

- `max_position_pct ∈ [0, 1]`
- `max_coverage_pct ∈ [0, 1]`
- `min_iv_rank_for_short_premium ∈ [0, 100]`
- `drawdown_tolerance ∈ [0, 1]`
- `risk_tolerance ∈ {"conservative", "moderate", "aggressive"}`
- `income_need ∈ {"low", "medium", "high"}`
- `style ∈ {"income", "balanced", "growth"}`

Out-of-range or invalid-enum values surface as 422 before the route handler runs.

---

## 13. `/outcomes` — manual outcome tracking (M1.17)

Outcomes implement the §9.10 learning-loop's Phase-1 manual path: after a decision plays out, the user records what actually happened (PnL realized, decision quality, error category if any, the regime that actually materialized). Each outcome row links 1:1 to a `daily_decisions` row via FK + UNIQUE.

In Phase 3, M3.5 will auto-fill outcomes from price history. For now they're manual entries.

### 13.1 `GET /outcomes?since=&limit=&cursor=`

Cursor-paginated list. Filtered to outcomes owned by the authenticated user transitively via `daily_decisions.user_id`.

```bash
$ curl -X GET "$API/outcomes?limit=20" -H "Authorization: Bearer $JWT"
{
  "outcomes": [
    {
      "id": "...",
      "daily_decision_id": "...",
      "evaluated_at": "2026-05-27T14:00:00Z",
      "horizon_days": 7,
      "pnl_realized": "1250.00",
      "pnl_unrealized": null,
      "decision_quality": "good",
      "error_type": "none",
      "actual_regime_realized": "HIGH_IV_PIN",
      "regime_match": true,
      "notes": "covered call expired worthless; collected full premium",
      "source": "manual"
    }
  ],
  "next_cursor": "eyJldmFsdWF0ZWRfYXQi..."
}
```

| Query param | Meaning | Default | Range |
|---|---|---|---|
| `since` | ISO 8601; filter out older outcomes | none | — |
| `limit` | page size | `50` | `[1, 200]` |
| `cursor` | opaque, from previous response's `next_cursor` | none | — |

The cursor is base64-encoded `{"evaluated_at": ISO, "id": UUID}` of the last row in the previous page. Treat it as **opaque** — server-side encoding can change without notice. Ordering is `(evaluated_at DESC, id DESC)` for stable cursors under same-second ties.

### 13.2 `POST /outcomes` — create

```bash
$ curl -X POST $API/outcomes \
    -H "Authorization: Bearer $JWT" \
    -d '{
      "daily_decision_id": "dd_a1b2c3d4e5f6_1748530200",
      "horizon_days": 7,
      "pnl_realized": "1250.00",
      "decision_quality": "good",
      "error_type": "none",
      "actual_regime_realized": "HIGH_IV_PIN",
      "regime_match": true,
      "notes": "covered call expired worthless"
    }'
```

| Status | When |
|---|---|
| `201` | Inserted; body is the persisted outcome |
| `404` | `daily_decision_id` doesn't exist OR doesn't belong to the authenticated user. The 404 is intentionally ambiguous — we don't leak which decisions exist for other users (§15 security posture). |
| `409` | An outcome for this `daily_decision_id` already exists. The UNIQUE constraint lives in the table (0001_init); the service catches the ON CONFLICT and maps to 409 rather than letting it bubble up as a 500 IntegrityError. |

The `source` field is server-set to `"manual"` and is not accepted in the request body. The `"auto"` source is reserved for the M3.5 auto-fill path.

### 13.3 `PATCH /outcomes/{outcome_id}` — partial update

```bash
$ curl -X PATCH $API/outcomes/abc-... \
    -H "Authorization: Bearer $JWT" \
    -d '{ "pnl_realized": "1340.00", "notes": "updated after settlement" }'
```

Only fields present in the body are updated. Omitted fields stay at their persisted values. Same 404 contract as POST — cross-user access doesn't leak existence.

`source` is immutable after insert (manual stays manual; M3.5 auto-fill happens via a separate code path, not by patching an existing manual outcome).

---

## 14. `/data/*/import-csv` — five CSV upload endpoints (M1.17)

Five endpoints, one per CSV resource per master plan §10. All use `multipart/form-data` with a single `file` field and return the same shape:

```json
{
  "inserted": 0,
  "updated": 0,
  "skipped": 0,
  "errors": [
    { "line": 5, "column": "kind", "message": "must be PUT or CALL; got 'BANANA'" }
  ],
  "validation_warnings": []
}
```

Per-row errors are reported in `errors[]` with 1-indexed line numbers (line 1 = header). The upload doesn't fail wholesale on a single bad row — good rows are inserted, bad rows are skipped, and the caller decides what to do with the report.

### 14.1 The 5 endpoints + idempotency strategies

| Endpoint | Idempotency | What happens on re-upload |
|---|---|---|
| `POST /data/positions/import-csv` | UPSERT on `(user_id, ticker, opened_at)` | Same lot opening → update `qty` + `avg_cost`; counts as `updated` |
| `POST /data/option-positions/import-csv` | UPSERT on 7-tuple `(user_id, ticker, side, kind, strike, expiry, opened_at)` | Same leg-opening event → update `qty` / `opened_price` / `status` |
| `POST /data/chain/import-csv` | Append-only with exact-match dedupe | Exact-match `(ticker, fetched_at, expiry, strike, kind)` → skip |
| `POST /data/iv/import-csv` | UPSERT on `(ticker, ts)` PK | Same date row → update OHLC + iv_rank/iv_percentile |
| `POST /data/events/import-csv` | Dedupe at upload on `(ticker, kind, scheduled_at, source)` | Exact-match → skip |

The composite UNIQUE constraints powering the first two upserts live in migration `0003_imp_unique_constraints`. The `iv_history` PK comes from `0001_init`. The other two tables don't have DB-level UNIQUE; deduplication happens at the application layer.

### 14.2 Canonical CSV headers (§10)

```
positions.csv          ticker,qty,avg_cost,opened_at
option_positions.csv   ticker,side,kind,strike,expiry,qty,opened_at,opened_price,status
chain.csv              ticker,fetched_at,expiry,strike,kind,bid,ask,last,oi,volume,iv,delta,gamma,theta,vega
iv_history.csv         ticker,ts,atm_iv_30d,iv_rank,iv_percentile,hv_30,high,low,close
events.csv             ticker,kind,scheduled_at,source,notes
```

Bytes-on-the-wire example:

```bash
$ cat positions.csv
ticker,qty,avg_cost,opened_at
MSFT,5000,400.12,2025-08-15T00:00:00Z

$ curl -X POST $API/data/positions/import-csv \
    -H "Authorization: Bearer $JWT" \
    -F "file=@positions.csv"
{ "inserted": 1, "updated": 0, "skipped": 0, "errors": [], "validation_warnings": [] }

# Re-upload the same file → 0 inserted, 1 updated (idempotent)
$ curl -X POST $API/data/positions/import-csv \
    -H "Authorization: Bearer $JWT" \
    -F "file=@positions.csv"
{ "inserted": 0, "updated": 1, "skipped": 0, "errors": [], "validation_warnings": [] }
```

### 14.3 §22.12 — IV history row-count validation

`POST /data/iv/import-csv` is the only CSV endpoint that runs a post-insert validation. After all rows are inserted/updated, the service counts the rows for each touched ticker and:

- **< 30 rows** → the entire upload is **rolled back** and the endpoint returns **422 `insufficient_iv_history`**. The engine's `iv_rank` and `iv_percentile` math is unreliable below 30 days.
- **30 ≤ count < 60** → upload succeeds with **200** but a soft warning lands in `validation_warnings[]` ("iv_percentile less reliable with <60 days").
- **60 ≤ count < 252** → upload succeeds with an info-level warning.
- **≥ 252 rows** → no warning.

The 422 case rolls back the transaction so a partially-uploaded ticker never leaves the DB in a sub-30-row state.

### 14.4 File size limit

V1 caps uploads at **10 MB** per file. Above that → HTTP 413 with `"file exceeds 10 MB limit"`. Production deployments can raise the cap by tuning `_MAX_FILE_BYTES` in `routers/data_import.py`. M2+ ingestion (provider abstraction) bypasses CSV entirely; this cap is a V1 protective measure.

---

## 15. `GET /market/{ticker}/latest` — convenience read-through (M1.17)

A **public** (no auth) endpoint that returns the most-recent market state for a ticker, built by reading the latest `option_chain_snapshots` + `iv_history` + `hv_history` + `events` rows and computing `max_pain` / `pcr_volume` / `pcr_oi` / `expected_move_pct` on-the-fly via engine primitives.

Per master plan §22.10. The endpoint does NOT invoke the engine pipeline — it's a thin read-through powering the Today screen's header and external integrations that want raw market context without a full `DailyDecision`.

```bash
$ curl -X GET $API/market/MSFT/latest
{
  "as_of": "2026-05-20T14:30:00Z",
  "ticker": "MSFT",
  "spot": "415.0",
  "iv_rank": 0.65,
  "iv_percentile": 0.60,
  "hv_30": 0.22,
  "expected_move_pct": 0.042,
  "max_pain": "415.0",
  "pcr_volume": 0.52,
  "pcr_oi": 0.48,
  "next_event": {
    "id": "...", "kind": "earnings",
    "scheduled_at": "2026-06-03T20:30:00Z",
    "ticker": "MSFT", "notes": null
  },
  "data_freshness": {
    "chain_age_seconds": 3600,
    "iv_age_seconds": 86400,
    "hv_age_seconds": 86400,
    "any_stale": false,
    "stale_tags": []
  }
}
```

### 15.1 Spot derivation (V1)

`option_chain_snapshots` has no per-snapshot `spot` column (§6 schema). V1 derives spot from the chain itself: the strike with the highest combined open interest at the nearest expiry. High-OI strikes cluster near ATM in practice, so this is a reasonable proxy. The same heuristic lives in `inputs_hydration_service` so both endpoints derive identical spot from the same DB state (replay determinism — see §16).

M2+ refinement: store spot explicitly when uploading the chain, or read from a separate `market_snapshots` table.

### 15.2 422 cases (§22.10)

| Trigger | Status | Body |
|---|---|---|
| No `option_chain_snapshots` rows for ticker | 422 | `"chain_not_yet_ingested: …"` |
| `iv_history` has < 30 rows for ticker | 422 | `"insufficient_iv_history: …"` |

Both 422 paths are the natural "user hasn't uploaded the prerequisite CSVs yet" signal. Clients prompt the user to upload via `/data/{chain, iv}/import-csv`.

### 15.3 §22.10 staleness thresholds

The `data_freshness` field reports how old the underlying data is, with named stale-tags applied above hard thresholds:

| Field | Threshold | Stale tag |
|---|---|---|
| `chain_age_seconds` | > 7200 (2h) | `"stale_chain"` |
| `iv_age_seconds` | > 90000 (~25h) | `"stale_iv"` |
| `hv_age_seconds` | > 90000 (~25h) | `"stale_hv"` |

`any_stale: true` when any field exceeds its threshold. The Today screen renders an amber badge when this fires.

---

## 16. The M1.17.5 hydration path — how `inputs` becomes optional

Before M1.17.5, every `/engine/daily-plan` call required the caller to supply a fully hydrated `EngineInputs` bundle. That worked for testing but didn't match the master plan's §7 `DailyPlanRequest = {ticker, as_of, use_cache}` shape. M1.17.5 closes the gap: when `inputs` is omitted, the API service hydrates from DB.

### 16.1 The hydration chain

```
POST /engine/daily-plan { ticker, as_of }      ← no inputs!
       │
       ▼
produce_and_persist(inputs=None) [decision_service.py]
       │
       ▼
hydrate_engine_inputs(session, user_id, ticker, as_of)  [inputs_hydration_service.py]
       │
       ├── _hydrate_chain_snapshot   ← all rows at latest fetched_at
       │                              from option_chain_snapshots
       │
       ├── _hydrate_profile          ← users.strategy_profile (or defaults)
       │
       ├── _hydrate_positions        ← positions + option_positions
       │                              aggregated into PositionState
       │                              (underlying_shares, has_short_call,
       │                              has_long_put, nearest dte/strike, …)
       │
       ├── _hydrate_market_state     ← engine.market_state.classify(…)
       │                              with iv_history (latest 2 rows for
       │                              iv_rank_change_1d) + hv_history +
       │                              events + chain-derived primitives
       │
       └── _hydrate_flow_score       ← engine.flow_score.compute(…)
                                      against the chain
       │
       ▼
EngineInputs → produce_daily_decision() → DailyDecision → persist
```

The hydration is byte-equivalent to what a caller would supply by hand from the same DB state. **`inputs_hash` is therefore deterministic** — same DB + same `as_of` → same hash → ON CONFLICT idempotency works as in the M1.14 path.

### 16.2 422 cases — missing prerequisites

The hydration raises `ValueError` for three prerequisite-missing cases that the router maps to HTTP 422:

| Error tag | Trigger | Client guidance |
|---|---|---|
| `missing_chain` | `option_chain_snapshots` empty for ticker | Upload chain.csv via `POST /api/v1/data/chain/import-csv` |
| `insufficient_iv_history` | `iv_history` < 30 rows for ticker (§22.12) | Upload more iv_history.csv |
| `missing_positions` | No positions AND no open `option_positions` for `(user_id, ticker)` | Upload positions.csv |

Recommended client flow: catch 422 with one of these tags, render a CTA to the upload page for the missing CSV.

### 16.3 V1 simplifying assumptions

A handful of `classify()` inputs require historical context that M1.17's CSV import doesn't yet populate. The V1 hydration punts on those with safe defaults:

| Field | V1 default | Reason |
|---|---|---|
| `breakout_signal` | `0.0` | Needs 5-day price + IV history + OI shift; M2+ refines |
| `oi_concentration_at_max_pain` | `0.0` | Needs OI distribution roll-up; engine accepts 0 safely |
| `gap_pct` | `null` | No daily-close tracking yet |
| `trend_strength` | `0.5` | Engine's own fallback for insufficient ADX history (§22.5) |
| `iv_rank_change_1d` | 2-row diff if available, else `0.0` | OK for V1 |
| `days_to_nearest_opex` | 3rd-Friday date arithmetic | Pure calendar math |

The contract is preserved: the engine still produces a coherent `DailyDecision`; the deterministic-replay guarantee holds (same DB state → same hash). All shortcuts are documented inline in `inputs_hydration_service.py`.

### 16.4 Choosing between the two shapes

| Use case | Recommended shape |
|---|---|
| Production Today screen | DB-hydrated (M1.17.5) — let the API do the work |
| Backtest harness | Hydrated body (M1.14) — supply scripted inputs |
| Calibration test fixtures | Hydrated body — exact replayability |
| What-if drilling with overrides | `/engine/what-if` with `overrides` (§7) |
| Demo / playground | DB-hydrated — fewer moving parts |

---

## 17. Plan deviations

Two of the seven endpoints' request shapes diverge from the master plan §7 reference. Both deviations are deliberate: the engine implementations went a different way during M1.7–M1.13, and the API layer prefers to match the engine over rewriting the engine to match a stale plan signature.

| Endpoint | Plan §7 says | Engine actually has | Why we kept the engine shape |
|---|---|---|---|
| `POST /engine/flow-score` | Takes a `UserStrategyProfile` so the recommended-action decision tree can read `profile.style` | `compute(chain_snapshot, spot, expiry_focus, dte_to_nearest_opex, ...)` — no profile | The V1 decision tree determines `recommended_action` from `score / gamma_risk / pin_probability` alone (§9.3a). Adding a profile parameter would force a no-op argument. |
| `POST /engine/strike-candidates` | Takes a high-level `intent: Literal["sell_call","buy_put","collar","sell_put"]` plus `market_state` + `flow_score` + `profile` | `select_strikes(action, chain_snapshot, risk_free_rate, dividend_yield)` — takes an `Action` from the recommendation pipeline | The recommendation pipeline already produces the `Action` with `target_delta` + `target_dte` baked in. The strike selector only needs those parameters, not the upstream context. Plan §9.4's `intent`-based signature would be a higher-level convenience layer to build later if useful. |

Both deviations are logged inline in `apps/api/app/schemas/decision.py` (the `FlowScoreRequest` and `ActionPayload` docstrings) and in the M1.15 and M1.16 PR bodies.

---

## 18. Hands-on exercises

### Exercise 1 — Replay verification

POST `/engine/daily-plan` twice with the same body. Verify:

1. Both responses have identical `decision.inputs_hash`.
2. Both responses have identical `decision.decision_id`.
3. The first response has `is_new_row: true`; the second has `is_new_row: false`.
4. `SELECT COUNT(*) FROM daily_decisions WHERE user_id = ?` reports exactly 1.

### Exercise 2 — What-if non-persistence

POST `/engine/what-if` twice with the same body. Verify:

1. Both responses have `is_new_row: false`.
2. `SELECT COUNT(*) FROM daily_decisions WHERE user_id = ?` is unchanged from before the first POST.

### Exercise 3 — Override semantics

POST `/engine/what-if` with `overrides: {}` and capture the response's `decision.inputs_hash`. Then POST again with `overrides: {"spot": 425.0}`. Verify the second `inputs_hash` differs from the first.

Then POST with `overrides: {"iv_rank": 1.5}` — verify 422 with a Pydantic range message. Then POST with `overrides: {"not_a_real_field": 1.0}` — verify 422 with the offending key in the title.

### Exercise 4 — End-to-end drill-down

For a chosen scenario (e.g. HIGH_IV_PIN with `breakout_signal=0.0`), call the four drill-down endpoints in order: market-state → flow-score → recommend → strike-candidates → execution-check. Then call `/daily-plan` once with the same upstream inputs. Verify the drill-down sequence's answers match the corresponding fields in the `/daily-plan` response (regime, score, emit, strike, fill confidence).

### Exercise 5 — Zero-leg emit

POST `/engine/strike-candidates` with `action.emit = "NO_OP"`. Verify the response has `legs: []` and `skipped_reason: "NO_OP emit code requires no new legs"` (or equivalent prose). Then POST `/engine/execution-check` with `legs: []`. Verify the response has `legs: []` and `aggregate_*` fields populated to the empty-input defaults.

---

## 19. Further reading

- **Master plan §7** — canonical endpoint table + request/response Pydantic schemas (the source of truth for request/response shapes).
- **Master plan §22.14** — what-if non-persistence contract.
- **Master plan §22.3** — extended 18-input `classify()` signature.
- **Master plan §9.3a** — V1 LOCKED Flow Score contract.
- **Master plan §9.4** — Strike Selector.
- **Master plan §9.8** — Execution Feasibility Module.
- **ADR-0001** — engine-first product framing.
- **ADR-0005** — pure-function engine discipline (no DB, no clock, no network).
- **ADR-0006** — RFC 7807 error envelope.
- **M1.14 PR** ([#45](https://github.com/csupenn/option-mgmt-2026/pull/45)) — daily-plan + recommend.
- **M1.15 PR** ([#47](https://github.com/csupenn/option-mgmt-2026/pull/47)) — what-if + market-state + flow-score.
- **M1.16 PR** ([#48](https://github.com/csupenn/option-mgmt-2026/pull/48)) — strike-candidates + execution-check.
- **M1.17 PR** ([#50](https://github.com/csupenn/option-mgmt-2026/pull/50)) — profile + outcomes + CSV imports + market/latest.
- **M1.17.5 PR** ([#51](https://github.com/csupenn/option-mgmt-2026/pull/51)) — `DailyPlanRequest.inputs` optional + DB hydration.
- **Master plan §9.9** — `UserStrategyProfile` validation rules.
- **Master plan §9.10** — Outcome Tracker / learning loop.
- **Master plan §10** — Canonical CSV formats.
- **Master plan §22.10** — `MarketLatestSnapshot` data source + staleness thresholds.
- **Master plan §22.12** — IV history validation policy.
- **Tutorials:** [Master Decision Engine](./master-decision-engine.md) covers everything happening inside `/engine/daily-plan`; the four upstream tutorials cover the modules wrapped by the sub-step endpoints.

---

## 20. Glossary

- **Action** — One emit code + parameters dict (`target_delta`, `target_dte`, `size_pct`, `urgency_days`) produced by the M1.9 rule pipeline. The unit the Strike Selector consumes.
- **ChainSnapshot** — Frozen point-in-time option chain projection: ticker + spot + as_of + tuple of `OptionContract`s. Carries everything the engine reads from the chain.
- **DailyDecision** — The persisted top-level result of `/engine/daily-plan`. Contains every intermediate sub-result (market state, flow score, recommendation, strike selections, executions) plus replay metadata.
- **decision_id** — Deterministic identifier `dd_<12hex>_<unix>` derived from `(inputs_hash, as_of_unix)`. Same inputs + same `as_of` → same `decision_id`.
- **EmittedAction** — Enum of action verbs: `SELL_COVERED_CALL_PARTIAL`, `ROLL_UP_AND_OUT`, `WHEEL_SHORT_PUT`, `BUY_LONG_DATED_PUT`, `OPEN_COLLAR`, `REDUCE_COVERAGE`, `MONETIZE_PUT`, `NO_OP`. The set of things the rule pipeline can emit.
- **Execution** — Per-leg + aggregate liquidity / spread / fill-confidence scoring. The output of `engine.execution.assess()` and of `/engine/execution-check`.
- **FlowScore** — V1 LOCKED 11-field contract (§22.2): signed `score`, `bullish_score`, `bearish_score`, `bias`, `recommended_action`, `pin_probability`, `gamma_risk`, `gamma_sign`, `confidence`, `explanation`, `breakdown`.
- **inputs_hash** — SHA-256 of the canonical-JSON-serialized engine inputs. Pinned in every persisted `DailyDecision`. See [Master Decision Engine tutorial §5](./master-decision-engine.md).
- **is_new_row** — Persistence-layer discriminant: `true` when `/daily-plan` actually wrote a new row; `false` when `ON CONFLICT DO NOTHING` fired. Always `false` for `/what-if`.
- **MarketStateResult** — Output of `engine.market_state.classify()`: chosen `Regime`, `regime_score`, `all_scores` map, `tags`, plus 18 echoed inputs.
- **overrides** — Flat dict on `/engine/what-if` requests; maps `MarketStateResultModel` field names to override values applied before the engine runs.
- **RecommendationResult** — Output of `engine.recommend()`: matched rule + emitted actions + rule-time confidence breakdown (without execution feasibility).
- **Regime** — One of `HIGH_IV_EVENT`, `HIGH_IV_PIN`, `LOW_IV_TREND`, `LOW_IV_RANGE`, `BREAKOUT`, `POST_EVENT_REPRICE`. The six-element controlled vocabulary classifying the current market.
- **StrikeLeg** — Concrete option leg picked by the strike selector: `OptionContract` + `LegSide` (`LONG` / `SHORT`) + match diagnostics (`delta_target`, `delta_actual`, `delta_distance`, `dte_actual`, `mid_price`).
- **StrikeSelection** — Output of `engine.strike_selector.select_strikes()`: echoed emit + 0..N `StrikeLeg`s + optional `skipped_reason`.
- **three-pin lock** — `(engine_version, weights_version, inputs_hash)`. Persisted on every `DailyDecision`. The combination guarantees byte-exact replay.
- **V1 hydration** — As of M1.17.5, `DailyPlanRequest.inputs` is optional; when omitted, the API service hydrates from DB via `inputs_hydration_service.hydrate_engine_inputs()`. See §16.
- **weights_version** — Version string of the active `weights.yaml` (currently `"v2.0"`). Bumped when the M1.10 multiplicative composer's weights change.

### Added in M1.17 + M1.17.5

- **CsvImportResponse** — Uniform shape across all 5 CSV upload endpoints: `{inserted, updated, skipped, errors, validation_warnings}`. Per-row failures are reported in `errors[]` with 1-indexed line numbers.
- **cursor (outcomes)** — Opaque base64-encoded `{evaluated_at, id}` tuple of the last row in the previous outcomes page. Server-side encoding can change without notice; clients pass it back verbatim.
- **data_freshness** — Per-input age stamps + staleness tags on `/market/{ticker}/latest` (and on `DailyDecision.data_freshness`). `any_stale: true` fires when any field exceeds its §22.10 threshold.
- **hydrate_engine_inputs** — M1.17.5 service function that builds an `EngineInputs` bundle from the latest DB rows and reproduces `market_state.classify` + `flow_score.compute` server-side. Same DB state → same hydrated bundle → same `inputs_hash` → ON CONFLICT idempotency holds.
- **insufficient_iv_history** — 422 error tag fired when `iv_history` has < 30 rows for the ticker (§22.12). Triggered by `/data/iv/import-csv` (post-insert validation, rolled back) and by `/engine/daily-plan` without `inputs` + by `/market/{ticker}/latest`.
- **missing_chain** — 422 error tag fired during hydration when `option_chain_snapshots` is empty for the ticker.
- **missing_positions** — 422 error tag fired during hydration when the user has no positions and no open option_positions for the ticker.
- **Outcome** — Manual entry tied 1:1 to a `daily_decisions` row via FK + UNIQUE. Records realized PnL, decision quality, error category, and the regime that actually materialized. Powers the §9.10 learning loop.
- **OutcomeSource** — `"manual"` (user entry) or `"auto"` (reserved for M3.5 auto-fill). Server-set on POST; immutable after insert.
- **ProfileUpdateRequest** — API-layer strict wrapper around `engine.profiles.UserStrategyProfile` with `extra="forbid"`. Surfaces typos like `max_postion_pct` as 422 rather than silently dropping them.
- **spot heuristic (V1)** — Both `/market/{ticker}/latest` and the hydration service derive spot as the strike with the highest combined OI at the nearest expiry (when no explicit spot column exists). High-OI strikes cluster near ATM. M2+ can refine by storing spot explicitly or reading from a dedicated market-data table.
- **stale_chain / stale_iv / stale_hv** — Staleness tags applied when the matching `*_age_seconds` exceeds the §22.10 thresholds (7200s for chain; 90000s for iv + hv).
- **UserStrategyProfile** — Frozen Pydantic model in `engine.profiles` describing the user's risk/income preferences + delta/DTE bands + drawdown tolerance + style. Persisted to `users.strategy_profile` JSONB. Hydrated into every `/engine/daily-plan` call.
