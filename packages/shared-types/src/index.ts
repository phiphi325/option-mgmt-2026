// Placeholder per plan v1.2 §22.15 L1 (day order: TS types before CI typecheck).
//
// M0.6 replaces this file with TypeScript types generated from Pydantic schemas
// in `apps/api/app/schemas` and `packages/engine/engine/types.py` via
// `packages/shared-types/scripts/generate.sh` (using datamodel-code-generator
// or equivalent).
//
// apps/web does NOT yet declare a workspace dependency on this package — the
// link is wired in M0.6 once real types exist. M0.4 only ensures the package
// is structurally present so CI in M0.5 can typecheck it cleanly.
export {};
