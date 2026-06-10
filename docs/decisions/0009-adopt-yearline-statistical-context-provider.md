# ADR-0009: Adopt yearline-universe as an external statistical-context provider

**Status**: Proposed
**Date**: 2026-06-10
**Plan ref**: addendum to v1.2; assessment in [`docs/enhancements/0002-yearline-context-assessment.md`](../enhancements/0002-yearline-context-assessment.md)
**Related code**: `packages/engine/engine/yearline/types.py` (future, OM-Y1), `apps/api/app/jobs/ingest_yearline.py` (future, OM-Y2), `apps/api/app/services/inputs_hydration_service.py` (future, OM-Y2), `engine.decision.produce_daily_decision` + `compute_inputs_hash` (future, OM-Y4)

## Context

**yearline-universe** is a ticker-agnostic, headless nightly batch that scores the MA250 "yearline"
repair/retry/trend situation per ticker and emits a small, versioned `YearlineContext` value object (a
persisted JSON artifact), flagged `must_not_auto_execute: true`. It supplies a **medium-horizon,
structural axis** (yearline repair vs trend, distance-to-MA250 + required rebound, conditional
days-to-touch, calibrated **gated** `P(retry ≤ H)`) that complements — and does not duplicate —
option-mgmt's short-horizon Market State (IV regime, dealer-gamma flow, ADX, breakout, event proximity).

option-mgmt already consumes pre-computed, validated value objects (`MarketStateResult`, `FlowScore`,
`ChainSnapshot`) computed *outside* the engine and passed *in* via the M1.17.5 hydration service. yearline
fits that exact slot. The producer side (yearline V13.8 adapter + the `YearlineContext` contract + JSON
schema + gated/stale fixtures + a separate `YearlineTrendSeries` presentation artifact) is **delivered**.

The full feasibility assessment (the four-test check + recommendation) is in
[`docs/enhancements/0002-yearline-context-assessment.md`](../enhancements/0002-yearline-context-assessment.md);
the verbatim source analysis is under [`docs/enhancements/yearline/`](../enhancements/yearline/). This ADR
records the binary decision + the boundary it locks.

## Decision

**Adopt yearline as an external statistical-context provider, phased C→A**, under five locked
constraints:

1. **Value-object boundary.** The engine consumes a frozen Pydantic `YearlineContext` value object —
   never the yearline library.
2. **Jobs-layer producer.** yearline (heavy, I/O) runs in the ingestion/jobs layer, persists its
   artifact; the **pure engine never imports it** (upholds ADR-0005; `check_no_broker_imports` + the
   coverage/version gates enforce it).
3. **Fourth replay pin.** A yearline-influenced decision folds `yearline_context_version` (a canonical
   hash of `{adapter_version, schema_version, model_stack_version}` + consumed fields) into replay
   identity, reusing `engine.decision.serialize_canonical`. A decision consuming **no** yearline context
   hashes **byte-identically** to the pre-OM-Y4 world (back-compat is acceptance-gated against the M1.24
   golden suite).
4. **Gate-respect.** `p_retry[h]` influences a decision **only where `gate_passed[h]`**; `p_success` /
   composite **only where `success_gate_passed`**; dormancy (`repair_active == False ⇒ p_retry == {}`)
   and `is_stale` are honest abstention, not zero. Enforced separately at the display and decision layers,
   each unit-tested.
5. **Two separate artifacts.** Scalar `YearlineContext` is the engine decision input (enters the replay
   hash); `YearlineTrendSeries` is presentation-only (the OM-Y3 trend plot; never enters the engine or
   the hash).

### Phased roadmap (each a separate, reviewed PR in option-mgmt-2026)

| Milestone | Deliverable | Decision impact |
|---|---|---|
| **OM-Y0** | This ADR + the enhancement assessment. **No code.** | none |
| **OM-Y1** | Frozen Pydantic `YearlineContext` + Pydantic→TS codegen + vendored fixtures + a contract test pinning the accepted `adapter_version`/`schema_version` range. | none (no behavior change) |
| **OM-Y2** | Alembic `yearline_context` table + `ingest_yearline.py` (idempotent) + hydration service → `YearlineContext \| None`. | none |
| **OM-Y3** | `GET /engine/yearline-context` + a read-only Today-screen evidence panel (card from `YearlineContext`, plot from `YearlineTrendSeries`). | **`DailyDecision` byte-identical** |
| **OM-Y4** | `produce_daily_decision(..., yearline_context=None)`; the 4th replay pin; new `rules.yaml` clauses + a gated Confidence-Composer component; engine-version + `weights_version` bump. | **output-changing → reviewed** |
| **OM-Y5** | *Stretch.* Market-State enrichment (Option B) or collar-intent keyed off yearline readiness. | ADR-level (see below) |

Per [`docs/phased-design/README.md`](../phased-design/README.md), the per-milestone OM-Y1…Y5 dev specs are
authored **when each milestone opens**, not now (premature design docs go stale).

## Consequences

### Positive

- A genuinely additive medium-horizon axis the short-horizon engine cannot derive — shapes
  defensive-vs-zero-cost collar intent, DTE selection, and directional bias.
- C (OM-Y3 read-only panel) delivers visible user value with **zero decision risk** and de-risks the
  contract before any decision logic depends on it.
- The boundary falls naturally out of option-mgmt's own design — yearline is "one more hydrated input,"
  not a re-architecture. ADR-0005 purity is preserved by construction.
- Determinism is preserved: yearline is deterministic, and the 4th pin keeps a yearline-influenced
  decision exactly replayable; no-yearline decisions are provably unchanged.

### Negative

- A versioned cross-repo **contract** to maintain (mitigated by a pinned version *range* + a contract
  test on both sides + a compatibility matrix).
- An **operational dependency**: the producer must run the **pooled-universe** nightly job (MSFT's gate
  trust depends on pooling), and a stale/missing artifact must degrade gracefully to `None`.
- OM-Y4's Confidence component is a real modelling choice under the multiplicative composer (ADR-0003) and
  bumps `weights_version` — coordination cost, reviewed.

### Neutral

- `gate_diagnostics` (AUC/MACE/n) is deliberately **off** the contract today; the card shows gate
  *status*, not model *performance*. Adding it later is a deliberate `ADAPTER_VERSION` + OM-Y1 pin bump.
- yearline remains independently useful beyond option-mgmt; the two repos coordinate **only** at the
  contract boundary.

## Alternatives considered

1. **Library import into `packages/engine`.** Rejected outright — violates ADR-0005 (heavy deps + I/O in
   a pure, lean module); breaks the coverage/version/no-broker gates. The whole integration hinges on
   *not* doing this.
2. **Monorepo merge (fold yearline into option-mgmt).** Rejected — drags the heavy deps, universe price
   cache, and proprietary data into the lean engine repo, kills yearline's standalone reuse, and conflates
   two release disciplines. See [`yearline/two_repo_strategy_and_deployment.md`](../enhancements/yearline/two_repo_strategy_and_deployment.md) §2.
3. **Go straight to OM-Y4 (gated consumption) without the read-only panel.** Rejected as the *first* step —
   C first delivers value sooner and de-risks the contract before decision logic depends on it. OM-Y4
   remains the goal, just not the opening move.
4. **Market-State enrichment (Option B) now.** Deferred — it touches the locked 6-regime taxonomy
   (ADR-0002) and would require an amendment. Revisit only if OM-Y4 proves the signal earns it (OM-Y5).
5. **Fold yearline into the E1–E9 enhancement roadmap (as "E10").** Rejected — yearline is a distinct
   *external system*, not one of the v1.2-spec analytical modules from `04-...spec-0509.md`. It gets its
   own ADR + `enhancements/yearline/` subfolder, cross-referenced from ADR-0008 rather than absorbed.

## References

- [`docs/enhancements/0002-yearline-context-assessment.md`](../enhancements/0002-yearline-context-assessment.md) — full feasibility assessment (the four-test check).
- [`docs/enhancements/yearline/`](../enhancements/yearline/) — verbatim source analysis + the delivered V13.8 producer handoff.
- [ADR-0001](./0001-engine-first-architecture.md) — engine-first architecture (yearline plugs into Layer 1 as a hydrated input).
- [ADR-0002](./0002-regime-taxonomy.md) — regime taxonomy (untouched by C→A; Option B would amend it).
- [ADR-0003](./0003-confidence-composer-multiplicative.md) — multiplicative composer (the OM-Y4 gated component lives within it; bumps `weights_version`).
- [ADR-0005](./0005-engine-pure-function-discipline.md) — engine purity (the hard boundary this ADR upholds).
- [ADR-0008](./0008-enhancement-adoption-roadmap.md) — the E1–E9 roadmap (yearline tracked separately as an external system).
- Plan v1.2 §16 (ingestion/jobs layer), §1 + §5 (engine-first boundary), M1.17.5 (`inputs_hydration_service`).
