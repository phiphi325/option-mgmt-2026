/**
 * Outcomes screen — the third Phase-1 surface per master plan §8 (M1.23).
 *
 * Server component. SSR-fetches page 1 of the user's outcomes via
 * `GET /outcomes` and hands them to the client-side `OutcomeTracker` (which owns
 * the manual-entry form, the paginated history, inline edit, and stats).
 * Mutations go through the `./actions` server actions, not this component.
 *
 * Mirrors `today/page.tsx` + `settings/page.tsx`: `force-dynamic` (per-user +
 * mutable; never cache, never prerender) so `cookies()` is not called during
 * `next build`. A 401 bubbles to `error.tsx`.
 */

import { OutcomeTracker } from "@/components/outcomes/OutcomeTracker";
import { getOutcomes } from "@/lib/api/outcomes";

export const dynamic = "force-dynamic";

export default async function OutcomesPage() {
  const { outcomes, next_cursor } = await getOutcomes({ limit: 50 });

  return (
    <main className="container mx-auto max-w-4xl py-12 px-4">
      <header className="mb-8 space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Outcomes</h1>
        <p className="text-sm text-muted-foreground">
          Record how each daily decision turned out and review your history.
          Outcomes close the learning loop the engine calibrates against.
        </p>
      </header>
      <OutcomeTracker initialOutcomes={outcomes} initialCursor={next_cursor} />
    </main>
  );
}
