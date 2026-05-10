# ADR-0006: RFC 7807 ProblemDetails as universal API error shape

**Status**: Accepted
**Date**: 2026-04-29 (implemented in M0.3)
**Plan ref**: v1.2 §7 (API endpoint design)
**Related code**:

- `apps/api/app/schemas/error.py` (`ProblemDetails` Pydantic model)
- `apps/api/app/main.py` (`HTTPException` handler + unhandled `Exception` handler)
- `apps/web/lib/api.ts` (`ApiError` class — unwraps RFC 7807 envelopes for the web client)

## Context

The API needs a consistent error shape that:

- Web clients can pattern-match on without parsing free-form strings.
- Future integrations (Slack bot in P4, brokerage callbacks in P4, third-party dashboards) understand without bespoke parsing.
- Distinguishes user-facing messages (`title`, `detail`) from machine-readable categorization (`type`, `status`).
- Carries arbitrary extension fields — e.g. `missing: ["iv_history.atm_iv_30d (52 days)"]` for HTTP 422 from `/engine/daily-plan` when IV history is too short.

Without a standard, every endpoint invents its own error shape and clients fragment.

## Decision

Adopt **RFC 7807 Problem Details for HTTP APIs** as the universal error envelope.

Schema (Pydantic, in `apps/api/app/schemas/error.py`):

```python
class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="allow")     # extension fields permitted
    type: str = "about:blank"     # URI categorizing the error
    title: str                    # short, human-readable summary
    status: int                   # HTTP status code
    detail: str | None = None     # human-readable explanation
    instance: str | None = None   # URI of the specific occurrence
```

Both `HTTPException` and unhandled `Exception` are mapped to this shape via FastAPI exception handlers in `apps/api/app/main.py`. **No 500 leaks raw stack traces or framework defaults.**

In `dev` mode (`Settings.is_dev=True`), `detail` includes the exception message. In production, `detail` is `None` for unhandled errors (the message could leak internals like file paths, library names, partial data).

Web client (`apps/web/lib/api.ts`) unwraps the envelope into an `ApiError` class:

```typescript
class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly title: string,
    public readonly detail?: string,
    public readonly extras?: Record<string, unknown>,
  ) { ... }
}
```

Type URIs use `about:blank` for generic errors and `https://errors.msft-engine.local/<slug>` for typed errors (M1.x onward, e.g. `https://errors.msft-engine.local/iv-solve-failed`).

## Consequences

**Positive**

- Clients rely on a stable shape across every error path.
- Debugging is faster: `instance` tells you exactly which URL produced the error; `type` enables programmatic dispatch on error categories without fragile string matching.
- Extension fields permit rich error context. M1.x examples:
  - `/engine/daily-plan` returns `{missing: [...]}` listing insufficient inputs.
  - `/engine/collar-builder` returns `{available_qty, required_qty}` when shares are insufficient.
- Standards-aligned: IETF RFC 7807 is well-understood by infrastructure tooling (load balancers, API gateways, observability platforms).

**Negative**

- Slightly more verbose than raw FastAPI `{"detail": "..."}` defaults.
- Custom error categories require minting a `type` URI; we use `about:blank` for now and reserve typed URIs for M1.x onward. Care needed not to fragment the type taxonomy.

**Neutral**

- All tests and clients written from M0.3 onward expect this shape; the test suite (`apps/api/tests/test_auth.py::test_login_returns_501_with_problem_envelope`) explicitly asserts on `body["status"] == 501` and `body["instance"]`.

## Alternatives considered

1. **FastAPI default `{"detail": str | object}`** — rejected: not a standard, no way to distinguish title/detail/extras, no machine-readable type, no `instance` URI for debugging.
2. **Custom envelope (`{"error": "...", "code": "..."}`)** — rejected: reinvents RFC 7807 worse and confuses anyone familiar with the standard.
3. **No envelope, HTTP status only** — rejected: clients need at least a human-readable message and ideally extension fields.
4. **GraphQL-style errors array (`{"errors": [{...}, ...]}`)** — rejected: this is REST, not GraphQL; mixing patterns confuses clients. RFC 7807 already supports multi-error context via extension fields.

## References

- Plan v1.2 §7 — API endpoint design (error envelope spec + worked example)
- IETF RFC 7807 — Problem Details for HTTP APIs (https://www.rfc-editor.org/rfc/rfc7807)
- `apps/api/app/schemas/error.py` — Pydantic schema
- `apps/api/app/main.py` — exception handlers (both `HTTPException` and `Exception`)
- `apps/web/lib/api.ts` — `ApiError` class
- `apps/api/tests/test_auth.py` — first integration tests asserting on the envelope shape
