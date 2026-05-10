# Documentation

Living documentation for option-mgmt-2026. Each file has a single owner and is updated as the codebase evolves; PRs that change behavior must update the relevant doc(s) in the same PR.

## Index

| Doc | Purpose |
|---|---|
| [engineering-principles.md](./engineering-principles.md) | **Read first.** Mandatory engineering principles + project-specific enforcement (SSOT, separation of concerns, contract-first, security, TDD, observability, simplicity). |
| [architecture.md](./architecture.md) | Layer cake + component map + data flow. Mirrors plan v1.2 §5. |
| [ssot-constants-map.md](./ssot-constants-map.md) | Canonical home for every shared constant. Define once, import everywhere. |
| [disclaimers.md](./disclaimers.md) | Full educational-use disclaimer text. Source of truth for `DisclaimerGate.tsx`, `DisclaimerFooter.tsx`, and the API's `DailyDecision.disclaimers[]`. |
| [decisions/](./decisions/) | Architecture Decision Records (ADRs). One file per locked decision. |

## Living plan document

The full development plan (20+ sections, audit-corrected to v1.2) lives in the Hyperagent thread `cmokf2twq0gsv06adlij0glqs`. **Section §22 is the canonical correction sheet** — read it before starting any milestone.

## Workflow

The required workflow (summary → tests → minimal change → run tests → update docs) is documented in `engineering-principles.md`. Every PR should:

- Reference the plan section(s) it implements (e.g., `Plan refs: v1.2 §17 M0.5, §22.13`).
- Update relevant `docs/` files in the same PR.
- Add or update an ADR in `docs/decisions/` if the change locks a new decision.
- Not introduce new dependencies without justification in the PR description.

## Future docs (planned)

- `docs/data-formats.md` — CSV import shapes (lands with M0.6 / M1.x).
- `docs/api/legacy.md` — legacy → canonical endpoint mapping (per v1.2 §22.1).
- `docs/operations.md` — runbooks, deploy procedures, on-call (Phase 2+).
- `docs/dev-log/YYYY-MM-DD.md` — daily what-shipped notes (per plan §19).
- `docs/models/` — ML model cards (Phase 4).
