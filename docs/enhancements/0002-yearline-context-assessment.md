# Yearline statistical-context — feasibility assessment & adoption recommendation

*Assessment + showing-of-work for adopting **yearline-universe** as an external statistical-context
provider. The binary decision + boundary lives in
[ADR-0009](../decisions/0009-adopt-yearline-statistical-context-provider.md); this document is the
analysis it references. Deep source analysis is preserved verbatim under
[`yearline/`](./yearline/). Educational research; not financial advice; neither system executes.*

---

## 0. Summary

| | |
|---|---|
| **Enhancement** | Adopt yearline-universe (MA250 "yearline" repair/retry statistical context) as an external, jobs-layer-hydrated, **gated** `YearlineContext` value object the pure engine optionally consumes. |
| **Recommendation** | **Adopt — phased, C→A.** Read-only evidence panel first (zero decision risk), then gated engine consumption. Market-State enrichment deferred (ADR-level). |
| **Boundary** | Producer runs in the **jobs/ingestion layer**; the pure engine **never imports yearline**. Coupling is a persisted, versioned artifact. |
| **Producer status** | yearline V13.8 adapter + `YearlineContext` contract + schema + gated/stale fixtures + `YearlineTrendSeries` — **delivered**. Consumer roadmap is unblocked. |
| **Roadmap** | OM-Y0 (this doc + ADR-0009) → OM-Y1 (contract) → OM-Y2 (ingest) → OM-Y3 (panel) → OM-Y4 (gated consumption) → OM-Y5 (stretch). |

---

## 1. What it adds that option-mgmt lacks

option-mgmt's Market State is **short-horizon** (IV regime, dealer-gamma flow, ADX, breakout, event
proximity, max-pain). yearline supplies a **complementary, medium-horizon, structural axis the engine
does not currently model**:

| option-mgmt today | yearline contributes | Why it matters to an overlay |
|---|---|---|
| Short-horizon market state | Medium-horizon structural state: yearline **repair vs trend** regime | a slower clock the engine doesn't model |
| no "distance to / recovery toward the 1-yr trend" | distance-to-MA250, **required rebound**, repair drawdown | frames drawdown-repair vs trend |
| no time-to-event estimate | conditional **days-to-next-touch** range | informs **expiry / DTE** selection |
| no probability of a structural retouch | calibrated, **gated** `P(retry ≤ H)` | informs **directional bias** + collar intent |

The two engines are **orthogonal time scales**, not redundant. Cultural fit is unusually strong: both
are engine-first, deterministic, auditable, no-execution, disclaimer-gated, and both follow a
"deterministic V1 → gated ML upgrade" discipline.

---

## 2. The four-test check

### Test 1 — Plan v1.2 conflict?

**No conflict for the recommended path (C→A); B conflicts and is deferred.**

- option-mgmt already consumes pre-computed value objects (`MarketStateResult`, `FlowScore`,
  `ChainSnapshot`) computed *outside* the engine and passed *in* (M1.17.5 `inputs_hydration_service`).
  yearline plugs into that **exact slot** — no new architectural pattern.
- **OM-Y4** adds an **optional kwarg** `yearline_context=None` to `produce_daily_decision`, mirroring the
  `futures_basis=0` stub the plan already plumbs (the Phase-4 "ML node-swap without interface churn"
  discipline). Additive; back-compat preserved.
- **OM-Y5 / Option B** (feeding yearline into the Market State classifier) **does** touch the locked
  6-regime taxonomy → an **ADR-0002 amendment**. Deferred; not part of adoption.

### Test 2 — Engineering principles?

**Passes, with one hard rule and two gated invariants.**

- **Engine purity (ADR-0005), the crux.** yearline is heavy (pandas/numpy/scipy/sklearn) + does I/O
  (price cache, universe pooling). It **cannot** be imported into `packages/engine`. It runs in the
  jobs layer, persists its envelope, and the engine sees only the lightweight value object.
  `check_no_broker_imports.sh` + the engine-version/coverage gates keep the boundary by construction.
- **No execution (I4).** Perfect alignment — yearline is `must_not_auto_execute: true`, evidence-only.
- **Determinism / replay (I3).** A yearline-influenced decision must fold the contract into replay
  identity via a **4th pin** `yearline_context_version` (a canonical hash of
  `{adapter_version, schema_version, model_stack_version}` + consumed fields). A decision consuming **no**
  yearline context must hash **identically** to the pre-OM-Y4 world (back-compat is acceptance-gated).
  The **M1.24 golden suite** is the natural regression guard, and `engine.decision.serialize_canonical`
  (shipped in M1.24) is the deterministic serializer the consumed-field hash should reuse.
- **Gate-respect (the most important rule), enforced at two layers:**
  - *Display (OM-Y3):* show `p_retry[h]` only where `gate_passed[h]`; render the rest as
    "withheld · building evidence" (never hidden — the withheld state is the signal).
  - *Decision (OM-Y4):* rules/confidence may read `p_retry[h]` **only where `gate_passed[h]`**; ungated
    → context-only. Each path is unit-tested independently; an ungated probability leaking into a
    decision is the worst-case failure mode.
  - Dormancy/staleness are honest abstention, not zero: `repair_active == False ⇒ p_retry == {}` (read
    `post_confirmation_trend_state`); `is_stale ⇒ treat as None`.
- **Pydantic→TS codegen drift gate (I7).** `YearlineContext` gets a frozen Pydantic model + generated TS,
  drift-checked in CI like `regimes.ts` / `profiles.ts`.

### Test 3 — Value vs. risk?

**High value, isolatable risk.**

- *Value:* a genuinely additive medium-horizon axis (repair/trend, days-to-touch, gated retry odds) that
  shapes defensive-vs-zero-cost collar intent, DTE selection, and directional bias — context the engine
  cannot currently derive. C delivers visible user value immediately; A is the prize.
- *Risk:* all **operational/contract**, not architectural — heavy-dep leakage (mitigated by the
  value-object boundary), schema drift (pinned version range + cross-repo contract test), stale/missing
  data (optional kwarg degrades gracefully), over-trusting an ungated probability (gate-respect, tested).

### Test 4 — Data dependency?

**Satisfiable; one operational obligation.**

- yearline needs a nightly **pooled-universe** run (single-ticker AUC ≈ 0.46 → pooled 0.74–0.82; MSFT's
  gate trust *depends* on pooling). So even for MSFT-only consumption, the producer must run the pooled
  job. The producer is deterministic and abstains gracefully (`is_stale`, `available:false`).
- Delivery is a persisted artifact (object store / release asset first; a Neon `yearline_context` table
  once OM-Y2 exists). Don't enable the producer's nightly cron until OM-Y2 can ingest it **and** a
  cross-repo contract test runs in CI — a daily artifact with no consumer is noise.

---

## 3. Two artifacts — keep them strictly separate

| Artifact | Shape | Role | In replay hash? |
|---|---|---|---|
| `YearlineContext` | scalar, flat | the **engine decision input** (OM-Y4) | **yes** (4th pin) |
| `YearlineTrendSeries` | parallel time-series arrays | **presentation only** — the OM-Y3 trend plot | **no** |

The scalar context powers the current-state **card**; the series powers the **line chart**. The series
never enters the engine or the replay hash, so the heavy chart payload never bloats the lean decision
contract. The OM-Y3 trend plot has its own rendering correctness contract (stacked panels per scale,
gap-don't-interpolate on `null`, right-edge ≠ card number, label-map internal enums) — see
[`yearline/producer-handoff/ux_trend_plot_support_analysis.md`](./yearline/producer-handoff/ux_trend_plot_support_analysis.md) §6.

**Deferred:** a `gate_diagnostics` block (AUC/MACE/n) is intentionally **not** on the contract. The card
shows gate *status* (trustworthy-now), not model *performance*. AUC belongs on an internal ops view;
adding it later is a deliberate `ADAPTER_VERSION` bump + coordinated OM-Y1 pin bump.

---

## 4. Recommendation

**Adopt, phased C→A.** Ship OM-Y0 (this assessment + ADR-0009) and OM-Y1 (the contract) first; then
OM-Y2→Y3 (ingest → read-only panel) for fast, zero-risk user value; then OM-Y4 (gated consumption) as
the reviewed, output-changing prize. Hold OM-Y5 / Option B (Market-State enrichment) for a future
ADR-0002 amendment, only if OM-Y4 proves the signal earns it.

The two genuinely delicate spots for the consumer side: (a) the replay-hash 4th pin with byte-identical
no-yearline back-compat (guarded by the M1.24 golden suite + `serialize_canonical`), and (b) gate-respect
enforced separately at the display and decision layers. Everything else is idiomatic to how option-mgmt
already hydrates value objects.

---

## 5. Open questions (carried into the relevant milestone)

1. **Delivery mechanism** — object store / release asset (loosest) vs a Neon `yearline_context` table
   (single source of truth). *Recommend* artifact-first, Neon table once OM-Y2 exists.
2. **Scope** — MSFT-only contract (matches Phase 1), universe-agnostic model; producer still runs the
   pooled job nightly.
3. **Which fields influence the decision (OM-Y4)** — display everything; let only **gated `p_retry[h]` +
   repair/trend state** influence rules/confidence at first; hold `p_success` / composite for later.
4. **Confidence-component shape (OM-Y4)** — ADR-0003's composer is multiplicative, so a yearline term is
   either a bounded **penalty multiplier** (defensive temper) or a **positive-score** contributor.
   *Recommend* start as a gated defensive temper; bumps `weights_version`.

## 6. References

- [ADR-0009](../decisions/0009-adopt-yearline-statistical-context-provider.md) — the adoption decision + boundary (canonical).
- [`yearline/assessment.md`](./yearline/assessment.md), [`yearline/integration_design_and_plan.md`](./yearline/integration_design_and_plan.md), [`yearline/two_repo_strategy_and_deployment.md`](./yearline/two_repo_strategy_and_deployment.md) — verbatim source analysis.
- [`yearline/producer-handoff/`](./yearline/producer-handoff/) — delivered V13.8 producer contract + UX trend-plot analysis.
- [ADR-0005](../decisions/0005-engine-pure-function-discipline.md) — engine purity (the hard boundary).
- [ADR-0002](../decisions/0002-regime-taxonomy.md) / [ADR-0003](../decisions/0003-confidence-composer-multiplicative.md) — taxonomy + composer (B touches the former; the OM-Y4 component touches the latter).
- [ADR-0008](../decisions/0008-enhancement-adoption-roadmap.md) — the E1–E9 enhancement roadmap (yearline is a distinct external system, tracked separately).
