/**
 * Settings screen — the second Phase-1 surface per master plan §8 (M1.22).
 *
 * Server component. Fetches the current `UserStrategyProfile` via
 * `GET /profile` (which always returns a profile — defaults for a fresh user)
 * and hands it to the client-side `UserStrategyProfileForm` as `initialProfile`
 * so the page renders fully populated with no client-side loading flash.
 *
 * Mutations are NOT done here — the form calls the `saveProfile` server action
 * (`./actions`) on Save.
 *
 * Error path: a 401 (no/expired session) bubbles to `error.tsx`, which renders
 * a sign-in prompt. Mirrors the Today screen's server-component + error-boundary
 * shape.
 */

import { UserStrategyProfileForm } from "@/components/settings/UserStrategyProfileForm";
import { getProfile } from "@/lib/api/profile";

export const dynamic = "force-dynamic"; // per-user + mutable; never cache, never prerender

export default async function SettingsPage() {
  const profile = await getProfile();

  return (
    <main className="container mx-auto max-w-2xl py-12 px-4">
      <header className="mb-8 space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Strategy settings</h1>
        <p className="text-sm text-muted-foreground">
          These inputs drive every recommendation. Changes take effect on your
          next daily plan.
        </p>
      </header>
      <UserStrategyProfileForm initialProfile={profile} />
    </main>
  );
}
