# ADR-0004: Disclaimer gate fails open under storage errors

**Status**: Accepted
**Date**: 2026-04-29 (implemented in M0.4)
**Plan ref**: v1.2 §15 (disclaimer enforcement)
**Related code**:

- `apps/web/components/today/DisclaimerGate.tsx`
- `apps/web/components/today/DisclaimerFooter.tsx`
- `apps/web/tests/disclaimer-gate.test.tsx` (the fail-open test case)
- [`docs/disclaimers.md`](../disclaimers.md)

## Context

The first-run disclaimer modal blocks the app until the user actively accepts. Per plan v1.2 §15, this is a hard gate — no ESC, no click-outside dismissal.

Acceptance is persisted via `localStorage.setItem("disclaimerAcceptedAt_v1", ...)`. But `localStorage` is not always available:

- Safari private mode rejects writes (and threw on reads in older versions).
- Some corporate DLP tools wrap or block `localStorage` access.
- Quota-exceeded errors on cleanup-resistant browsers.
- Future: SSR contexts where `window` is undefined (we render the gate as a client component, but defensive coding still helps).

If we treat any storage error as "user has not accepted", the modal blocks forever in those environments. Users cannot use the app at all.

## Decision

When `localStorage.setItem` or `localStorage.getItem` throws, **fail open** — allow the app to render normally as if the user had accepted.

Concrete behavior:

- The `useEffect` that reads localStorage on mount wraps the call in `try/catch`. On error, treat as accepted (`setAccepted(true)`).
- The `accept()` handler wraps `localStorage.setItem` in `try/catch`. On error, accepts in-memory for the session and continues.
- The persistent footer (`DisclaimerFooter.tsx`) is **always** rendered, regardless of gate state. It is a plain server-rendered component requiring no JavaScript and no storage access.

The fail-open path means a small subset of users may use the app without ever explicitly tapping "I understand". This is mitigated by:

1. The persistent footer always shows the short-form disclaimer.
2. M1.x: every API response includes the disclaimer text in `DailyDecision.disclaimers[]`.
3. M1.x: the `users.disclaimer_accepted_at` DB column (already in the M0.2 schema) replaces localStorage as the source of truth for authenticated sessions; storage errors won't apply once auth is in place.

## Consequences

**Positive**

- App is usable in privacy-restricted environments (Safari private, corp DLP, etc.).
- No infinite-loop bug class where storage refuses both reads and writes and the modal cannot progress.
- Persistent footer + future API-side disclaimer injection preserves the legal posture across the failure path.

**Negative**

- Small compliance gap: some users may use the app without explicitly tapping "I understand" in the modal.
- The audit trail for "did this user see the disclaimer" is incomplete in M0.4 (localStorage-only). M1.x's DB column closes this gap for authenticated sessions.

**Neutral**

- Deliberate UX tradeoff documented in the gate's source docstring and validated by a dedicated test (`tests/disclaimer-gate.test.tsx::test_failopen_on_storage_error`) that mocks both `getItem` and `setItem` to throw.

## Alternatives considered

1. **Hard fail** (block app on storage error) — rejected: punishes users for browser settings outside the app's control; produces a hostile first impression.
2. **Silent retry with exponential backoff** — rejected: doesn't help when localStorage is genuinely unavailable; hides the issue from users who could otherwise switch browsers.
3. **Server-side acceptance flag** instead of localStorage — rejected for M0.4 (no auth yet); planned for M1.x via `users.disclaimer_accepted_at` (already in the M0.2 migration).
4. **Cookie-based acceptance** — rejected: cookies face similar restrictions in privacy-restricted environments AND add SSR complexity (cookie reads in server components require explicit `cookies()` calls).

## References

- Plan v1.2 §15 — Disclaimer enforcement
- `apps/web/components/today/DisclaimerGate.tsx` (docstring documents this decision inline)
- `apps/web/tests/disclaimer-gate.test.tsx` (test case 4)
- [`docs/disclaimers.md`](../disclaimers.md) — canonical disclaimer text + implementation rules
