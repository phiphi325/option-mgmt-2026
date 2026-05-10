# Disclaimers

The full educational-use disclaimer text. **This file is the source of truth.** When the text changes, every consumer updates in the same PR.

## Consumers

- `apps/web/components/today/DisclaimerGate.tsx` — first-run modal.
- `apps/web/components/today/DisclaimerFooter.tsx` — persistent footer on every page.
- `apps/api` API responses — every `DailyDecision.disclaimers[]` carries the canonical strings (M1.x).
- M0.6+ extracts these to `apps/web/lib/disclaimers.ts` so the UI imports rather than inlines.

## Short form (footer + API field)

```
Educational only · Not financial advice · Verify with broker and advisor · Data may be delayed or inaccurate
```

## Full form (modal + about page)

This tool provides decision-support and education about options strategies. It is **not** financial advice. Options involve substantial risk, including loss of principal.

By continuing you confirm you understand:

- This is **educational, not advice**.
- Options carry **substantial risk**.
- You will **verify with a licensed advisor and broker** before any trade.
- Data shown may be **delayed or inaccurate**.
- **No outcome is guaranteed**.

## Legal posture

The product is a **decision-support tool** for the user's own decisions. It is not a broker, advisor, RIA, or financial planner. Users retain full responsibility for every action they take.

Before any paid offering of this product:

- Legal review of the disclaimer text.
- Consultation with state securities counsel re: RIA status.
- Possible SOC 2 / regulatory review depending on user data handling.

## Implementation rules

- The disclaimer modal cannot be dismissed via ESC or click-outside (per plan v1.2 §3 hard contract).
- Acceptance is persisted in localStorage in M0.4 (`disclaimerAcceptedAt_v1` key); M1.x replaces this with the `users.disclaimer_accepted_at` DB column already in the M0.2 migration.
- The disclaimer **fails open** when localStorage is unavailable (Safari private mode, corp DLP). The persistent footer is still always visible. Documented in [ADR-0004](./decisions/0004-disclaimer-fail-open.md) once written; for now in `DisclaimerGate.tsx` docstring.
- Every API response that returns recommendations (M1.x) includes the short-form disclaimer as a string in `DailyDecision.disclaimers[]` — so API consumers see it too.

## Maintenance

When you change the text:

1. Update **this file** first.
2. Update `apps/web/components/today/DisclaimerGate.tsx` (modal text).
3. Update `apps/web/components/today/DisclaimerFooter.tsx` (footer text).
4. Update `apps/api/app/schemas/...` (the `disclaimers` field default values, M1.x).
5. Update any tests that assert on the text.
6. All in the same PR.

After M0.6+: only step 1 + step 4 (canonical TS file) remain; gate/footer import from `apps/web/lib/disclaimers.ts`.
