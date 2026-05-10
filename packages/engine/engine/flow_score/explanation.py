"""Human-readable explanation builder for FlowScore.

Per plan v1.2 §9.3a `render_explanation()`. The explanation is one of
the V1 LOCKED fields on `FlowScore` (§22.2) — it's persisted, surfaced
in the Today screen UI, and read by Recommendation Engine rationale
templates.

The string is **stable across patch bumps**: changing the wording is a
minor-bump change because UI snapshot tests and downstream NLP /
disclosure templates may anchor on phrases. Adding sentences is fine;
restructuring is not.

V1 sentence templates (each line one sentence, joined by spaces):

  - "FlowScore composite: +<S>." where S = score with sign, 1 dp
  - "OI walls at <support>/<resistance>" / "OI support at <s>" / "OI
    resistance at <r>" / "No significant OI walls identified."
  - "Dealer gamma net short (magnitude <g.score>) — vol amplifier." or
    "Dealer gamma net long (magnitude <g.score>) — vol dampener."
    (omitted when sign == 0)
  - "High pin probability (<pp>) near max pain."
    (omitted when pp < 0.6)

Pure function (per ADR-0005).
"""

from __future__ import annotations

from engine.scoring import GammaScoreResult, OiWalls

# Pin-probability threshold for the explanation sentence. Below this,
# the "high pin probability" sentence is omitted — matches the same
# threshold used by `bias_from_score` to bucket pin_risk.
_PIN_EXPLAIN_THRESHOLD = 0.6


def render_explanation(
    *,
    walls: OiWalls,
    score: float,
    gamma: GammaScoreResult,
    pin_probability: float,
) -> str:
    """Build the explanation string for a `FlowScore`.

    Args:
        walls: OI walls (from `compute_oi_walls`).
        score: Signed composite score in [-100, 100].
        gamma: Gamma score result (from `gamma_score`).
        pin_probability: In [0, 1]; the `sigmoid_pin` output.

    Returns:
        A space-joined sentence string. Always at least 2 sentences
        (composite + walls); up to 4 (composite + walls + gamma + pin).
    """
    parts: list[str] = []
    parts.append(f"FlowScore composite: {score:+.1f}.")

    if walls.support is not None and walls.resistance is not None:
        parts.append(
            f"OI walls at {walls.support:.2f} (support) / "
            f"{walls.resistance:.2f} (resistance)."
        )
    elif walls.support is not None:
        parts.append(
            f"OI support at {walls.support:.2f}; no clear resistance."
        )
    elif walls.resistance is not None:
        parts.append(
            f"OI resistance at {walls.resistance:.2f}; no clear support."
        )
    else:
        parts.append("No significant OI walls identified.")

    if gamma.sign == -1:
        parts.append(
            f"Dealer gamma net short (magnitude {gamma.score:.2f}) — "
            f"vol amplifier."
        )
    elif gamma.sign == +1:
        parts.append(
            f"Dealer gamma net long (magnitude {gamma.score:.2f}) — "
            f"vol dampener."
        )
    # sign == 0 → no gamma sentence

    if pin_probability >= _PIN_EXPLAIN_THRESHOLD:
        parts.append(
            f"High pin probability ({pin_probability:.2f}) near max pain."
        )

    return " ".join(parts)
