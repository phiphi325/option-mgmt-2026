# Architecture Decision Records (ADRs)

Locked decisions for the option-mgmt-2026 codebase. Each ADR is short (1 page) and references the full plan section for context.

## Index

| # | Title | Status | Plan ref |
|---|---|---|---|
| [0001](./0001-engine-first-architecture.md) | Engine-first architecture | Accepted | v1.2 §1 + §5 |
| [0002](./0002-regime-taxonomy.md) | Regime taxonomy locked to 6 regimes | Accepted | v1.2 §9.1 + §22 |
| [0003](./0003-confidence-composer-multiplicative.md) | Confidence Composer uses multiplicative penalties | Accepted | v1.2 §22.13 |
| [0004](./0004-disclaimer-fail-open.md) | Disclaimer gate fails open under storage errors | Accepted | v1.2 §15 |
| [0005](./0005-engine-pure-function-discipline.md) | `packages/engine` pure-function discipline (no I/O) | Accepted | v1.2 §1 + §5 + §16 |
| [0006](./0006-rfc-7807-error-envelope.md) | RFC 7807 ProblemDetails as universal API error shape | Accepted | v1.2 §7 |
| [0007](./0007-python-version-pin.md) | Python 3.14 pinned across api + engine | Accepted | v1.2 §17 M0.5, §22.15 |

## Adding an ADR

1. Pick the next four-digit number.
2. Use the template:

   ```markdown
   # ADR-XXXX: <decision>

   **Status**: Proposed | Accepted | Superseded by ADR-YYYY
   **Date**: YYYY-MM-DD
   **Plan ref**: v1.2 §X
   **Related code**: list canonical files

   ## Context
   ## Decision
   ## Consequences
   ## Alternatives considered
   ## References
   ```

3. Update this index.
4. Reference the ADR in the PR that locks the decision.

## Status definitions

- **Proposed** — under review.
- **Accepted** — locked. Code changes that violate the ADR require an updated ADR (or a new one that supersedes it).
- **Superseded** — replaced by a later ADR. Keep the old ADR for history; link to the superseder in its `Status:` line.
