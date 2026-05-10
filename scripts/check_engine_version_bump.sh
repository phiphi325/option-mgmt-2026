#!/usr/bin/env bash
#
# CI guard — engine_version bump policy.
#
# Per `docs/engineering-principles.md` (Contract-First) and ADR-0005
# (engine pure-function discipline): any change under packages/engine/engine/
# MUST also bump packages/engine/engine/version.py:__version__ so every
# persisted DailyDecision can be replayed against a known engine version.
#
# Bump conventions:
#   patch  (0.x.y → 0.x.y+1)   bug fix, no schema change
#   minor  (0.x.0 → 0.x+1.0)   new engine, score, public function
#   major  (x.0.0 → x+1.0.0)   schema change, removed/renamed fields, semantic shift
#
# Skips when no engine files changed (no-op for PRs that don't touch the engine).
# Skips silently when packages/engine/engine/ doesn't yet exist (pre-M0.6 era).
#
# In CI (PR builds): compares against the merge base on origin/$GITHUB_BASE_REF.
# Locally (pre-commit): compares staged changes to the index.
#
# Plan refs: v1.2 §22.15 L2,
#            ADR-0005 (engine pure-function discipline),
#            docs/engineering-principles.md (Contract-First).

set -euo pipefail

ENGINE_DIR="packages/engine/engine"
VERSION_FILE="$ENGINE_DIR/version.py"

# Pre-M0.6: nothing to check yet.
if [ ! -d "$ENGINE_DIR" ]; then
    echo "OK: $ENGINE_DIR does not exist yet (pre-M0.6); skipping."
    exit 0
fi

# Determine base ref. In GitHub Actions PR runs, GITHUB_BASE_REF is the target.
BASE_REF="${GITHUB_BASE_REF:-main}"

# Try to fetch the base ref shallowly if it's missing.
if ! git rev-parse "origin/$BASE_REF" >/dev/null 2>&1; then
    git fetch origin "$BASE_REF" --depth=1 >/dev/null 2>&1 || true
fi

MERGE_BASE=$(git merge-base "origin/$BASE_REF" HEAD 2>/dev/null || echo "")

if [ -n "$MERGE_BASE" ]; then
    # CI / merge-base mode
    CHANGED=$(git diff --name-only "$MERGE_BASE"..HEAD -- "$ENGINE_DIR/" || true)
    BUMP_LINES=$(git diff "$MERGE_BASE"..HEAD -- "$VERSION_FILE" 2>/dev/null \
        | grep -c '^+__version__' || true)
else
    # Local pre-commit mode: look at staged changes.
    CHANGED=$(git diff --cached --name-only -- "$ENGINE_DIR/" 2>/dev/null || true)
    BUMP_LINES=$(git diff --cached -- "$VERSION_FILE" 2>/dev/null \
        | grep -c '^+__version__' || true)
fi

if [ -z "$CHANGED" ]; then
    echo "OK: no $ENGINE_DIR/ changes detected."
    exit 0
fi

if [ "${BUMP_LINES:-0}" -lt 1 ]; then
    echo "ERROR: changes detected in $ENGINE_DIR/ but __version__ was not bumped." >&2
    echo "" >&2
    echo "Per docs/engineering-principles.md (Contract-First) and ADR-0005:" >&2
    echo "any change to $ENGINE_DIR/ MUST also update $VERSION_FILE" >&2
    echo "with a bumped __version__ value." >&2
    echo "" >&2
    echo "Bump conventions:" >&2
    echo "  patch  (0.x.y → 0.x.y+1)  bug fix, no schema change" >&2
    echo "  minor  (0.x.0 → 0.x+1.0)  new engine, score, public function" >&2
    echo "  major  (x.0.0 → x+1.0.0)  schema change, removed/renamed fields, semantic shift" >&2
    echo "" >&2
    echo "Changed engine files:" >&2
    echo "$CHANGED" | sed 's/^/  /' >&2
    exit 1
fi

echo "OK: $ENGINE_DIR/ changes accompanied by __version__ bump."
