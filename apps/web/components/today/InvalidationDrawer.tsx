/**
 * "What invalidates this?" drawer (M1.21) — a thin wrapper around
 * `RationaleDrawer`, sourced from `recommendation.invalidation`. Named as its
 * own file for the same reason as `RisksDrawer`.
 */

import { RationaleDrawer } from "./RationaleDrawer";

interface Props {
  items: readonly string[];
}

export function InvalidationDrawer({ items }: Props) {
  return <RationaleDrawer label="What invalidates this?" items={items} />;
}
