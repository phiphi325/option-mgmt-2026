# ADR-0002: Regime taxonomy locked to 6 named regimes

**Status**: Accepted
**Date**: 2026-04-29
**Plan ref**: v1.2 §9.1 + §22.14 M4
**Related code**:

- `apps/api/app/db/migrations/versions/0001_init.py` (Postgres `regime` enum)
- `packages/engine/engine/regimes.py` (Python enum, M0.6+)
- `packages/shared-types/src/regimes.ts` (TS enum, generated, M0.6+)
- `apps/web/tailwind.config.ts` (semantic colors)
- `apps/web/app/globals.css` (CSS variables)

## Context

Without a controlled set, regime labels would drift ad-hoc. That makes:

- Testing hard (no canonical fixtures to assert on).
- Scoring inconsistent across decisions over time.
- ML retraining (Phase 4) painful — the classification target needs a fixed schema.
- UI design hard — every regime needs a stable visual identity.

## Decision

Lock the regime taxonomy to **six named regimes**:

| Regime | Triggers | Allowed strategies |
|---|---|---|
| `HIGH_IV_EVENT` | IVR ≥ 70 AND event ≤ 7d | OPEN_COLLAR, SELL_COVERED_CALL_PARTIAL, ROLL_OUT, TRIM_COVERAGE_POST_EVENT |
| `HIGH_IV_PIN` | IVR ≥ 60 AND `|spot−max_pain|/spot ≤ 1%` AND DTE ≤ 5 | SELL_COVERED_CALL_TIGHT, ROLL_PIN_AWARE, IRON_FLY_BIAS |
| `LOW_IV_TREND` | IVR ≤ 30 AND ADX-style trend ON | BUY_LONG_DATED_PUT, REDUCE_COVERAGE, RATIO_CALL_SPREAD |
| `LOW_IV_RANGE` | IVR ≤ 30 AND realized ≈ implied AND no trend | SELL_COVERED_CALL_PARTIAL, WHEEL, SHORT_STRANGLE_SIZED |
| `BREAKOUT` | Price breaks key level + volume + OI shift + post-event IV crush | ROLL_UP_AND_OUT, REDUCE_COVERAGE, MONETIZE_PUT |
| `POST_EVENT_REPRICE` | T+0/T+1 after binary event AND IV crush AND gap | RE_STRIKE_COLLAR, SELL_RICHER_SKEW_PREMIUM, ROLL_INTO_NEW_VOL |

**Three canonical homes** (cross-language SSOT):

1. **Postgres**: `CREATE TYPE regime AS ENUM (...)` in `0001_init.py`. Shipped M0.2.
2. **Python**: `class Regime(str, Enum)` in `packages/engine/engine/regimes.py`. M0.6+.
3. **TypeScript**: generated from Python via `packages/shared-types/scripts/generate.sh`. M0.6+.

**Six semantic UI colors** (per plan v1.2 §8):

- `HIGH_IV_EVENT` → amber
- `HIGH_IV_PIN` → slate
- `LOW_IV_TREND` → emerald
- `LOW_IV_RANGE` → sky
- `BREAKOUT` → violet
- `POST_EVENT_REPRICE` → rose

CSS variables live in `apps/web/app/globals.css`; Tailwind tokens (`bg-regime-breakout`, etc.) wire into `apps/web/tailwind.config.ts`. Components NEVER reference raw hex.

## Consequences

**Positive**

- Testable: 24 regime fixtures (per plan v1.2 §13) check classification against expected labels.
- ML-ready: Phase 4 HMM/transformer trains on `(features, regime_label)` pairs from a fixed alphabet.
- UI-consistent: every regime has one color across light + dark themes.
- Schema-validated: Postgres rejects bad values on `outcomes.actual_regime_realized` (per v1.2 §22.14 M4).

**Negative**

- Adding a new regime requires (a) migration, (b) Python enum, (c) TS regen, (d) UI color, (e) at least 4 new fixtures. The coupling is intentional.

**Neutral**

- `market_states.regime` is `text` (not enum) per plan §6 — application layer validates against the 6 enum values. A follow-up migration could tighten this.

## Alternatives considered

1. **Free-text regime labels** — rejected: ad-hoc drift, no validation, no ML target.
2. **More regimes (12+)** — rejected: harder to reach statistical significance per regime, harder for users to internalize. The six chosen cover the 95th percentile of useful options-trading market states.
3. **Continuous "regime score" instead of discrete labels** — rejected: less explainable in UI, harder to map to allowed strategies, harder to test.

## References

- Plan v1.2 §9.1 — Regime Taxonomy (locked)
- Plan v1.2 §22.14 M4 — `outcomes.actual_regime_realized` typed as enum
- Plan v1.2 §8 — semantic regime colors in the UI
