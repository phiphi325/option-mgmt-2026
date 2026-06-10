#!/usr/bin/env bash
# Fail CI / pre-commit when packages/engine/engine/version.py gains a new
# __version__ value but CHANGELOG.md does NOT gain a corresponding
# top-level `## [x.y.z] — YYYY-MM-DD` entry for the new version.
#
# Closes the drift class that produced the M1.11a / M1.11b CHANGELOG gap
# documented in docs/thread-transitions/2026-05-13-t03-m1.11b-doc-sync.md.
#
# Sibling to scripts/check_engine_version_bump.sh, which fires when an
# engine/ change lands without bumping __version__. This guard fires when
# __version__ bumps without a matching CHANGELOG entry.
#
# Per M1.24 dev spec (docs/phased-design/phase-1/m1.24-master-decision-goldens.md)
# § "Bundled companion tooling".

set -euo pipefail

# Determine the diff range. In pre-commit we look at staged changes; in CI
# (GitHub Actions) we look at changes between HEAD and the merge-base with
# main / staging.
if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  # CI mode: compare against origin/main (or origin/staging if that's the
  # base). The CI workflow fetches full history (fetch-depth: 0) so this
  # merge-base lookup succeeds.
  BASE_REF="${GITHUB_BASE_REF:-main}"
  # Try the standard origin/$BASE_REF; fall back to $BASE_REF if origin/
  # is missing (push-to-main workflow runs).
  if git rev-parse --verify "origin/${BASE_REF}" >/dev/null 2>&1; then
    BASE="origin/${BASE_REF}"
  elif git rev-parse --verify "${BASE_REF}" >/dev/null 2>&1; then
    BASE="${BASE_REF}"
  else
    echo "check_changelog_entry: cannot resolve base ref '${BASE_REF}'; skipping."
    exit 0
  fi
  DIFF_ARGS="${BASE}...HEAD"
else
  # Local pre-commit mode: staged diffs.
  DIFF_ARGS="--cached"
fi

# Skip cleanly when version.py wasn't touched.
if ! git diff $DIFF_ARGS --name-only -- 'packages/engine/engine/version.py' | grep -q .; then
  exit 0
fi

# Extract the NEW __version__ string from the diff. We grep for the added
# `+__version__: str = "x.y.z"` line and capture the version. If multiple
# such adds appear (unusual), pick the last (chronologically latest).
NEW_VERSION=$(
  git diff $DIFF_ARGS -- packages/engine/engine/version.py \
    | grep -E '^\+__version__' \
    | sed -E 's/^\+__version__:[[:space:]]*str[[:space:]]*=[[:space:]]*"([^"]+)"$/\1/' \
    | tail -1
)
if [[ -z "${NEW_VERSION}" ]]; then
  echo "check_changelog_entry: ERROR: packages/engine/engine/version.py changed but"
  echo "  the new __version__ value was not parseable from the diff."
  echo "  Expected an added line like: +__version__: str = \"x.y.z\""
  exit 1
fi

# Look for the matching `## [x.y.z] — YYYY-MM-DD` header added to CHANGELOG.md.
# The em-dash (—, U+2014) is required to match the existing entries' style.
if git diff $DIFF_ARGS -- CHANGELOG.md \
   | grep -qE "^\+## \[${NEW_VERSION//./\\.}\] — [0-9]{4}-[0-9]{2}-[0-9]{2}"; then
  echo "check_changelog_entry: OK (engine ${NEW_VERSION} ↔ CHANGELOG entry present)"
  exit 0
fi

echo "check_changelog_entry: ERROR"
echo "  packages/engine/engine/version.py bumped __version__ to ${NEW_VERSION},"
echo "  but CHANGELOG.md does not gain a matching top-level header"
echo "    '## [${NEW_VERSION}] — YYYY-MM-DD'"
echo "  Add the entry above the previous version's header and re-commit."
echo
echo "  Per docs/phased-design/phase-1/m1.24-master-decision-goldens.md"
echo "  § 'Bundled companion tooling'."
exit 1
