"""Engine version — bumped per scripts/check_engine_version_bump.sh policy.

Bump conventions (per ADR-0005 + plan v1.2 §22.15 L2):

  patch (0.x.y → 0.x.y+1)   bug fix, no schema change
  minor (0.x.0 → 0.x+1.0)   new engine, score, public function
  major (x.0.0 → x+1.0.0)   schema change, removed/renamed fields, semantic shift

Every persisted DailyDecision pins this version + weights_version + inputs_hash
for exact replay. Changing this value is not free — CI verifies it bumps on any
change under packages/engine/engine/.
"""

from __future__ import annotations

__version__: str = "0.3.0"
