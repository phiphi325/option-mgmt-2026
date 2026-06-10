"""Jobs / ingestion layer (apps/api).

Heavy, I/O-bound producers run here — NOT in `packages/engine` (ADR-0005). The
engine consumes only the lightweight, validated value objects these jobs
persist. `ingest_yearline` lands the nightly yearline-universe artifact (OM-Y2).
"""
