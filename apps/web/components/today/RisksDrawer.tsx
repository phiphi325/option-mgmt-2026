/**
 * "Risks" drawer (M1.21) — a thin wrapper around `RationaleDrawer` with a
 * fixed label, sourced from `recommendation.risks`. Named as its own file so
 * the master-plan §8 component tree can import it by semantic name and future
 * per-section customisation doesn't require editing `RationaleDrawer`.
 */

import { RationaleDrawer } from "./RationaleDrawer";

interface Props {
  items: readonly string[];
}

export function RisksDrawer({ items }: Props) {
  return <RationaleDrawer label="Risks" items={items} />;
}
