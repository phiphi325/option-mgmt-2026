/**
 * Collapsible bullet section for the Today screen (M1.21) — used for "Why"
 * (rationale), "Risks", and "What invalidates this?".
 *
 * Built on the native `<details>`/`<summary>` element: keyboard-accessible
 * (focusable summary, toggled by Enter/Space) and collapsible with **zero
 * dependencies and no client JS** — the repo has no shadcn `Collapsible` (only
 * `ui/button` + `ui/dialog`), and a native disclosure is the right primitive
 * for an inline card section. `defaultOpen` maps to the `open` attribute.
 * Renders nothing when `items` is empty (no empty drawers).
 */

import { cn } from "@/lib/utils";

interface Props {
  /** "Why" | "Risks" | "What invalidates this?" */
  label: string;
  items: readonly string[];
  /** Open on first render (the "Why" drawer is open by default). */
  defaultOpen?: boolean;
  className?: string;
}

function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function RationaleDrawer({ label, items, defaultOpen = false, className }: Props) {
  if (!items || items.length === 0) return null;
  const slug = slugify(label);

  return (
    <details open={defaultOpen} className={cn("group px-3", className)} data-testid={`drawer-${slug}`}>
      <summary
        className="flex cursor-pointer items-center justify-between py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        data-testid={`drawer-trigger-${slug}`}
      >
        {label}
      </summary>
      <ul className="space-y-1.5 pb-3 pl-1" data-testid={`drawer-content-${slug}`}>
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-muted-foreground">
            <span className="mt-0.5 shrink-0 text-xs" aria-hidden>
              •
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
