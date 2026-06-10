# Yearline contract fixtures (OM-Y1)

Vendored **verbatim** from the yearline-universe repo's V13.8 adapter
(`exports/yearline_context/`) — the cross-repo contract test's golden inputs.
Per ADR-0009 + [`docs/enhancements/0002-yearline-context-assessment.md`](../../../../../docs/enhancements/0002-yearline-context-assessment.md).

| File | Shape | Role |
|---|---|---|
| `fixture_msft_gated.json` | gated MSFT example (`repair_active: true`, all horizons `gate_passed`) | the trustworthy-now case |
| `fixture_stale_empty.json` | abstention shape (`repair_active: false`, `p_retry: {}`, `is_stale: true`) | the no-usable-context case |
| `yearline_context_schema.json` | the producer's JSON schema (reference only) | drift record; not validated in-test (engine stays jsonschema-free) |

`test_yearline_contract.py` parses both fixtures into `engine.yearline.YearlineContext`
and pins the accepted `adapter_version` / `schema_version` range. A producer-side
`adapter_version` bump (or any field-shape change under `extra="forbid"`) breaks
this test — the intended cross-repo drift guard.

**Do not hand-edit.** These mirror the producer's emitted bytes; refresh them only
on a coordinated yearline release + an `ACCEPTED_*_VERSIONS` pin bump in
`engine/yearline/types.py`.
