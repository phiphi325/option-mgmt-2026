/**
 * One recommended action, rendered as a list row (M1.19).
 *
 * Layout:
 *  - Header: strategy label (via `formatStrategy`) + an `ExecutionBadge` for
 *    the first execution leg when present.
 *  - Body, `OPEN_COLLAR` (with a resolved `collar_structures[i]`): the two
 *    collar legs (long put + short call) side by side, plus the net
 *    debit/credit.
 *  - Body, otherwise: the action's generic `parameters` (the engine types them
 *    as `dict[str, Any]`; we render them generically — typed renderers per
 *    emit code are a future enhancement, see M1.19 dev spec open question #2).
 *
 * Presentational (no `"use client"`, matching `MarketStateBadge` /
 * `StrategyTitle`).
 */

import { ExecutionBadge } from "./ExecutionBadge";
import { formatStrategy } from "@/lib/strategy-labels";
import { formatStrike, formatPremium } from "@/lib/format";
import type { Action, CollarLeg, CollarStructure, Execution } from "@/lib/decision-types";

interface Props {
  action: Action;
  /** Per-action aggregate execution; `null` when the engine produced no legs. */
  execution: Execution | null;
  /** Non-null only for `OPEN_COLLAR` emits with a feasible structure. */
  collarStructure: CollarStructure | null;
  index: number;
}

export function ActionRow({ action, execution, collarStructure, index }: Props) {
  // Narrow `collarStructure` directly in the JSX conditional (a separate
  // boolean would not narrow it under strict TS).
  const isCollar = action.emit === "OPEN_COLLAR" && collarStructure !== null;
  const headerLeg = execution?.legs?.[0] ?? null;
  const parameters = action.parameters ?? {};

  return (
    <li
      className="flex flex-col gap-2 rounded-md border border-border bg-card p-3"
      data-testid={`action-row-${index}`}
      data-emit={action.emit}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold">{formatStrategy(action.emit)}</span>
        {headerLeg && <ExecutionBadge leg={headerLeg} />}
      </div>

      {isCollar && collarStructure ? (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <CollarLegDetail label="Buy put" leg={collarStructure.long_put} />
          <CollarLegDetail label="Sell call" leg={collarStructure.short_call} />
          <div className="col-span-2 flex justify-between text-muted-foreground">
            <span>{collarStructure.net_debit_credit < 0 ? "Net credit" : "Net debit"}</span>
            <span className="font-medium tabular-nums text-foreground">
              {formatPremium(collarStructure.net_debit_credit)}
            </span>
          </div>
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">
          {Object.entries(parameters).length === 0 ? (
            <span className="italic">No parameters</span>
          ) : (
            Object.entries(parameters).map(([k, v]) => (
              <span key={k} className="mr-3 inline-block">
                {k}: <span className="tabular-nums text-foreground">{String(v)}</span>
              </span>
            ))
          )}
        </div>
      )}
    </li>
  );
}

function CollarLegDetail({ label, leg }: { label: string; leg: CollarLeg }) {
  return (
    <div className="rounded bg-muted/50 p-2" data-testid={`collar-leg-${leg.kind.toLowerCase()}`}>
      <p className="font-medium">{label}</p>
      <p className="tabular-nums">
        {formatStrike(leg.strike)} · {leg.expiry}
      </p>
      <p className="text-muted-foreground">Δ {leg.delta.toFixed(2)}</p>
      <p className="tabular-nums">{formatPremium(leg.premium)}</p>
    </div>
  );
}
