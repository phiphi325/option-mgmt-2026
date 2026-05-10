# ADR-0003: Confidence Composer uses multiplicative penalties

**Status**: Accepted
**Date**: 2026-05-09
**Supersedes**: original Confidence Composer formula in plan v1.0 / v1.1
**Plan ref**: v1.2 §22.13
**Related code**:

- `packages/engine/engine/confidence/__init__.py` (M0.6+)
- `packages/engine/engine/config/weights.yaml` (`version: v2.0`, M0.6+)
- `apps/api/app/core/config.py` — `Settings.weights_version = "v2.0"` (already shipping in M0.3)

## Context

The v1.0 / v1.1 Confidence Composer used a **subtractive penalty** formula:

```
raw = w_flow * flow_alignment + w_struct * structure_alignment +
      w_regime * regime_match + w_signal * signal_alignment
    - w_event * event_risk_penalty - w_liquidity * illiquidity_penalty
```

with the constraint `Σ|w| = 1.0`.

The audit in plan v1.2 §22.13 noted that the achievable raw range under this formula is `[-0.20, +0.80]`, NOT `[-1, +1]` or `[0, 1]`. After `clip01()`:

- Maximum possible confidence = **0.80** (never 1.0).
- A user seeing `confidence: 0.78` is at 97.5% of max — but the UI displays it as "78%" which is misleading.

## Decision

Switch to **multiplicative penalties** so the achievable confidence range is true `[0, 1]`:

```
positive = w_flow*flow_alignment + w_struct*structure_alignment
         + w_regime*regime_match + w_signal*signal_alignment
            (positive_weights sum to 1.0)

penalty_mult = (1 - p_event * event_risk_penalty)
             * (1 - p_liquidity * illiquidity_penalty)

confidence = clip01(positive * penalty_mult)
```

`weights.yaml v2.0` defaults:

```yaml
version: "v2.0"
positive_weights:        # sum = 1.0
  flow:    0.30
  struct:  0.25
  regime:  0.25
  signal:  0.20
penalty_caps:            # max reduction each penalty can apply
  event:    0.30         # event_risk_penalty=1.0 reduces confidence by up to 30%
  liquidity: 0.25        # illiquidity_penalty=1.0 reduces confidence by up to 25%
```

The `ConfidenceBreakdown` payload exposes two new fields so the UI can render the penalty as a darker overlay reducing the bar's effective width:

- `positive_score` — pre-penalty value in `[0, 1]`
- `penalty_multiplier` — applied multiplier in `[0.45, 1.0]` (worst-case 1 − 0.30 − 0.25 + cross-product, slightly higher when only one penalty fires)

## Consequences

**Positive**

- True `[0, 1]` confidence range: when shown as 78%, it really IS 78% of the maximum achievable.
- More intuitive UI: penalties multiplicatively cap rather than subtract from a sum, which matches users' mental model of "this thing reduces my confidence by ~10%".
- Symmetric: 0% penalty = no reduction; 100% penalty (capped at 30% / 25%) = max reduction. Clear ceiling per dimension.
- Decomposable: the breakdown shows `positive_score` and `penalty_multiplier` separately so the user can see what drove the final value.

**Negative**

- Backward incompatible: any v1.x decisions in storage are at a different scale. M0.6+ replay tests must distinguish `weights_version` v1.0 vs v2.0 outputs.
- Re-tuning needed: the v2.0 default weights are an initial guess; calibration against historical outcomes (Phase 3 outcome auto-fill, Phase 4 ML weight recalibration) will update them.

**Neutral**

- The same six confidence components (flow, struct, regime, signal, event, liquidity) still feed in. Only their composition changes.

## Alternatives considered

1. **Normalize subtractive output to [0,1]** (audit Option A) — produces `confidence / 0.80` but hides the true scale; rejected for being a UI hack rather than a real fix.
2. **Allow weights to sum to >1** (e.g. `Σ|w_pos| = 1.0` and penalties unconstrained) — rejected: even less intuitive than the original.
3. **Drop penalties entirely, use positive-only weighted sum** — rejected: event risk and illiquidity are real headwinds; suppressing them gives false confidence.

## References

- Plan v1.2 §22.13 — Confidence Composer redesign
- Audit report `03-msft-decision-engine-plan-analysis-0509.md` §8 — math correctness analysis (the audit was right on this point)
- Original deferred decision: Plan v1.1 §9.7 — `Σ|w| = 1.0` constraint was the bug
