#!/usr/bin/env bash
#
# CI guard from plan v1.2 §22.1 — fails when apps/web/package.json drifts off
# the locked Next.js version. Wired into CI in M0.5 and into pre-commit alongside
# `check_engine_version_bump.sh`.
#
# Update this single constant to pin a new version.
set -euo pipefail

EXPECTED="16.2.6"
PKG="apps/web/package.json"

if [[ ! -f "$PKG" ]]; then
    echo "ERROR: $PKG not found (run from repo root)" >&2
    exit 1
fi

# Use jq if available, otherwise grep/sed.
if command -v jq >/dev/null 2>&1; then
    actual=$(jq -r '.dependencies.next // .devDependencies.next // ""' "$PKG")
else
    actual=$(grep -E '"next"\s*:\s*"' "$PKG" | head -1 | sed -E 's/.*"next"\s*:\s*"([^"]+)".*/\1/')
fi

if [[ "$actual" != "$EXPECTED" ]]; then
    echo "ERROR: Next.js pin drifted." >&2
    echo "  Expected: $EXPECTED (locked in plan v1.2 §22.1)" >&2
    echo "  Actual:   $actual" >&2
    echo "" >&2
    echo "Either update apps/web/package.json back to $EXPECTED, or update" >&2
    echo "EXPECTED in scripts/check_next_version.sh + plan §22.1 if intentional." >&2
    exit 1
fi

echo "OK: next@$EXPECTED pin matches plan v1.2 §22.1"
