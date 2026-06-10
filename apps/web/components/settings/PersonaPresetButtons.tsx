"use client";

/**
 * Persona quick-start buttons for the Settings screen (M1.22).
 *
 * Each button fills the form with a preset `UserStrategyProfile` via `onSelect`
 * — it does NOT save. The parent (`UserStrategyProfileForm`) decides what to do
 * with the profile (here: load it into the controlled form so the user can
 * review and tweak before pressing Save).
 *
 * Dependency-free (M1.22 Path A): the spec used shadcn `<Tooltip>` for the
 * persona description, which isn't installed. We use the native `title`
 * attribute instead — a zero-dependency hover/affordance that screen readers
 * also surface.
 */

import { Button } from "@/components/ui/button";
import type { UserStrategyProfile } from "@/lib/decision-types";
import { PERSONAS } from "@/lib/personas";

interface Props {
  /** Called with the full profile when a preset is clicked. Does NOT save. */
  onSelect: (profile: UserStrategyProfile) => void;
}

export function PersonaPresetButtons({ onSelect }: Props) {
  return (
    <div className="space-y-2" data-testid="persona-presets">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        Quick start — apply a preset (you can still edit before saving)
      </p>
      <div className="flex flex-wrap gap-2">
        {Object.entries(PERSONAS).map(([key, persona]) => (
          <Button
            key={key}
            type="button"
            variant="outline"
            onClick={() => onSelect(persona.profile)}
            title={persona.description}
            data-testid={`persona-${key}`}
          >
            {persona.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
