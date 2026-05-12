# Tutorial: Engine API Reference (`/api/v1/engine/*`)

> **Audience.** Full-stack engineers integrating against the engine HTTP surface; first-year master's students who have read the engine-layer tutorials and now want to see how those modules are exposed; reviewers of the M1.14 / M1.15 / M1.16 pull requests.
> **Prerequisites.** Read at least the [Master Decision Engine](./master-decision-engine.md) tutorial first. Familiarity with the upstream engine tutorials ([Market State](./market-state-engine.md), [Flow Score](./flow-score-engine.md), [Confidence Composer](./confidence-composer.md), [Scoring Primitives](./scoring-primitives.md)) is recommended but not strictly required for the API surface alone.
> **Reading time.** ~35 min careful read with the exercises; ~15 min skim.
> **Coverage.** All seven engine endpoints shipped through M1.16 (commit [`726ec37`](https://github.com/csupenn/option-mgmt-2026/commit/726ec37f1542083260293b968ef0ee2439757086) on `main`, 2026-05-12). Engine version `1.4.0`; API version stamped on `/version`.
>
> **Disclaimer.** This tutorial is **educational material**. The endpoints documented here are decision-support; they do not place trades, do not check broker margin, and do not constitute investment advice. See [`docs/disclaimers.md`](../disclaimers.md).

---

## Table of contents

1. [Why a separate API tutorial?](#1-why-a-separate-api-tutorial)
2. [The seven endpoints at a glance](#2-the-seven-endpoints-at-a-glance)
3. [Authentication](#3-authentication)
4. [Error envelope (RFC 7807)](#4-error-envelope-rfc-7807)
5. [`POST /engine/daily-plan` — the primary endpoint (M1.14)](#5-post-enginedaily-plan--the-primary-endpoint-m114)
6. [`POST /engine/recommend` — rule pipeline only (M1.14)](#6-post-enginerecommend--rule-pipeline-only-m114)
7. [`POST /engine/what-if` — transient evaluation (M1.15)](#7-post-enginewhat-if--transient-evaluation-m115)
8. [The four sub-step endpoints (M1.15 + M1.16)](#8-the-four-sub-step-endpoints-m115--m116)
9. [Idempotency, replay, and the three-pin lock](#9-idempotency-replay-and-the-three-pin-lock)
10. [The V1 hydration story](#10-the-v1-hydration-story)
11. [End-to-end worked example](#11-end-to-end-worked-example)
12. [Plan deviations](#12-plan-deviations)
13. [Hands-on exercises](#13-hands-on-exercises)
14. [Further reading](#14-further-reading)
15. [Glossary](#15-glossary)

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

## 2. The seven endpoints at a glance

| Endpoint | Milestone | Wraps | Persists? | Auth |
|---|---|---|---|---|
| `POST /engine/daily-plan` | M1.14 | `engine.produce_daily_decision()` | Yes (idempotent via `ON CONFLICT`) | Required |
| `POST /engine/recommend` | M1.14 | `engine.recommend()` | No | Required |
| `POST /engine/what-if` | M1.15 | `engine.produce_daily_decision()` | **Never** (§22.14) | Required |
| `POST /engine/market-state` | M1.15 | `engine.market_state.classify()` | No | Required |
| `POST /engine/flow-score` | M1.15 | `engine.flow_score.compute()` | No | Required |
| `POST /engine/strike-candidates` | M1.16 | `engine.strike_selector.select_strikes()` | No | Required |
| `POST /engine/execution-check` | M1.16 | `engine.execution.assess()` | No | Required |

Two of the eight §7 sub-step endpoints are still pending:

- `POST /engine/collar-builder` (M1.16a) — blocked on M1.11a engine module.
- `GET /market/msft/latest` (M1.16b) — deferred until M1.17 lands the CSV-import path that feeds it.

Once both ship, all of §7 is HTTP-reachable.

### 2.1 Mental model — primary vs. transient vs. drill-down

The seven endpoints fall into three categories:

```
┌─────────────────────────────────────────────────────────┐
│  PRIMARY (persists)                                     │
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
```

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

## 5. `POST /engine/daily-plan` — the primary endpoint (M1.14)

The headline endpoint. Runs the full Master Decision Engine and (by default) persists a `daily_decisions` row.

### 5.1 Request

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

| Field | Type | Default | Notes |
|---|---|---|---|
| `ticker` | `str` (1–10 chars) | `"MSFT"` | MSFT-only in V1; reserved for multi-ticker post-M4.11. |
| `as_of` | ISO 8601 datetime | server `now(UTC)` | Decision timestamp. Pinned for replay. |
| `inputs` | `EngineInputs` | required | Full hydrated bundle. See §10 for the V1 hydration story. |
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

## 12. Plan deviations

Two of the seven endpoints' request shapes diverge from the master plan §7 reference. Both deviations are deliberate: the engine implementations went a different way during M1.7–M1.13, and the API layer prefers to match the engine over rewriting the engine to match a stale plan signature.

| Endpoint | Plan §7 says | Engine actually has | Why we kept the engine shape |
|---|---|---|---|
| `POST /engine/flow-score` | Takes a `UserStrategyProfile` so the recommended-action decision tree can read `profile.style` | `compute(chain_snapshot, spot, expiry_focus, dte_to_nearest_opex, ...)` — no profile | The V1 decision tree determines `recommended_action` from `score / gamma_risk / pin_probability` alone (§9.3a). Adding a profile parameter would force a no-op argument. |
| `POST /engine/strike-candidates` | Takes a high-level `intent: Literal["sell_call","buy_put","collar","sell_put"]` plus `market_state` + `flow_score` + `profile` | `select_strikes(action, chain_snapshot, risk_free_rate, dividend_yield)` — takes an `Action` from the recommendation pipeline | The recommendation pipeline already produces the `Action` with `target_delta` + `target_dte` baked in. The strike selector only needs those parameters, not the upstream context. Plan §9.4's `intent`-based signature would be a higher-level convenience layer to build later if useful. |

Both deviations are logged inline in `apps/api/app/schemas/decision.py` (the `FlowScoreRequest` and `ActionPayload` docstrings) and in the M1.15 and M1.16 PR bodies.

---

## 13. Hands-on exercises

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

## 14. Further reading

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
- **Tutorials:** [Master Decision Engine](./master-decision-engine.md) covers everything happening inside `/engine/daily-plan`; the four upstream tutorials cover the modules wrapped by the sub-step endpoints.

---

## 15. Glossary

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
- **V1 hydration** — Current convention: every engine endpoint accepts the full input bundle in the request body. M1.17+ optionally hydrates from Postgres when fields are omitted.
- **weights_version** — Version string of the active `weights.yaml` (currently `"v2.0"`). Bumped when the M1.10 multiplicative composer's weights change.
