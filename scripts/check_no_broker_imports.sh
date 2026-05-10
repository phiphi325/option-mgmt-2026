#!/usr/bin/env bash
#
# CI guard — no broker write paths.
#
# Per `docs/engineering-principles.md` (Security by Design) and ADR-0001
# (engine-first, no execution): this codebase MUST NOT contain any
# broker-write capabilities. Phase 4 may add read-only IBKR integration
# (positions sync, market data) but write paths require:
#   - explicit codeowner approval
#   - a new ADR superseding the no-execution invariant
#   - removal of this guard from CI (so the change is visible)
#
# Fails the build if any forbidden import or call is detected anywhere in
# apps/ or packages/.
#
# Plan refs: v1.2 §15 (no-execution guard rails),
#            ADR-0001 (engine-first, no execution),
#            docs/engineering-principles.md (Security by Design).

set -euo pipefail

# Forbidden patterns. Keep this list tight — false positives erode trust.
# Pattern format is a literal string (grep -F), not a regex.
FORBIDDEN_PATTERNS=(
    # IBKR write methods (ibapi, ib_insync)
    "placeOrder("
    "place_order("
    "cancelOrder("
    "cancel_order("
    "modifyOrder("
    "modify_order("
    # Alpaca write methods (alpaca-py)
    "submit_order("
    "replace_order("
    # Direct broker SDK imports — write-capable libraries.
    # If a read-only adapter is introduced later, prefer wrapping HTTP calls
    # over the SDK so this guard stays meaningful.
    "from ibapi"
    "import ibapi"
    "from ib_insync"
    "import ib_insync"
    "from alpaca"
    "import alpaca"
    # Generic suspicious patterns
    "import broker_client"
    "from broker_client"
)

# Files to scan. Limited to source files in apps/ and packages/ — avoids
# false positives in docs/, scripts/, and YAML configs.
SCAN_GLOB=(
    --include='*.py'
    --include='*.ts'
    --include='*.tsx'
    --include='*.js'
    --include='*.mjs'
)

EXIT_CODE=0
echo "Scanning apps/ packages/ for forbidden broker patterns..."

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    matches=$(grep -rnF "$pattern" apps/ packages/ "${SCAN_GLOB[@]}" 2>/dev/null || true)
    if [ -n "$matches" ]; then
        echo "" >&2
        echo "ERROR: forbidden broker pattern '$pattern' detected:" >&2
        echo "$matches" >&2
        EXIT_CODE=1
    fi
done

if [ $EXIT_CODE -eq 0 ]; then
    echo "OK: no broker-write imports or calls detected."
fi

exit $EXIT_CODE
