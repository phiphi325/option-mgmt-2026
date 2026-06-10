/**
 * Persona presets for the Settings screen (M1.22).
 *
 * The three personas are educational fixtures embedded in the frontend — they
 * are NOT stored per-user (they are starting points a user can apply and then
 * tweak, never personalised data). Clicking a preset fills the
 * `UserStrategyProfileForm`; the user reviews and clicks Save to persist.
 *
 * Each profile is a complete, valid `UserStrategyProfile` on the **real**
 * engine schema (8 fields). They are deliberately spread across the enum space
 * so the demo shows visibly different inputs:
 *   - Helen → income / moderate, high coverage, collar-biased (defensive income)
 *   - Ravi  → growth / aggressive, low coverage, plain covered calls (let it run)
 *   - Diana → balanced / conservative, modest coverage, waits for high IV, collars
 *
 * NOTE (M1.22 spec divergence): the shipped dev spec encoded an OLDER profile
 * shape (`max_coverage`, `roll_aggressiveness`, `tax_sensitivity`,
 * `delta_target_band`, `dte_band_days`). Those fields do not exist on the
 * engine's `UserStrategyProfile` and would 422 against `PUT /profile`. These
 * presets use the real fields verified against `engine/profiles.py` and the
 * API's `ProfileUpdateRequest`.
 */

import type { UserStrategyProfile } from "@/lib/decision-types";

export interface Persona {
  readonly label: string;
  readonly description: string;
  readonly profile: UserStrategyProfile;
}

export const PERSONAS: Record<"helen" | "ravi" | "diana", Persona> = {
  helen: {
    label: "Helen",
    description:
      "Income-focused, moderate risk. High coverage and a collar bias for downside protection.",
    profile: {
      risk_tolerance: "moderate",
      income_need: "high",
      max_position_pct: 0.5,
      max_coverage_pct: 0.8,
      min_iv_rank_for_short_premium: 50,
      prefer_collars_over_covered_calls: true,
      drawdown_tolerance: 0.1,
      style: "income",
    },
  },
  ravi: {
    label: "Ravi",
    description:
      "Growth-focused, higher risk tolerance. Lighter coverage on a partial position and plain covered calls.",
    profile: {
      risk_tolerance: "aggressive",
      income_need: "low",
      max_position_pct: 0.6,
      max_coverage_pct: 0.3,
      min_iv_rank_for_short_premium: 35,
      prefer_collars_over_covered_calls: false,
      drawdown_tolerance: 0.25,
      style: "growth",
    },
  },
  diana: {
    label: "Diana",
    description:
      "Balanced and conservative. Modest coverage, waits for high IV before selling premium, prefers collars.",
    profile: {
      risk_tolerance: "conservative",
      income_need: "medium",
      max_position_pct: 0.4,
      max_coverage_pct: 0.5,
      min_iv_rank_for_short_premium: 60,
      prefer_collars_over_covered_calls: true,
      drawdown_tolerance: 0.1,
      style: "balanced",
    },
  },
};
