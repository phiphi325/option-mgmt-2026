"use client";

/**
 * One outcome in the history (M1.23). Renders a read-only summary; "Edit" swaps
 * in the shared `OutcomeFields` and `PATCH`es via the `patchOutcome` server
 * action, then hands the updated row back to the parent.
 *
 * The outcome carries no decision summary (the `/outcomes` API returns only
 * `daily_decision_id` — see the M1.23 dev spec), so the row shows the truncated
 * decision UUID + the outcome fields. P&L renders from the **string** wire form
 * via `formatPnl`.
 */

import { useState } from "react";

import { patchOutcomeAction } from "@/app/outcomes/actions";
import { Button } from "@/components/ui/button";
import { OutcomeFields } from "@/components/outcomes/OutcomeFields";
import { formatPnl } from "@/lib/format";
import {
  type OutcomeFormValues,
  formValuesToPatchInput,
  outcomeToFormValues,
} from "@/lib/outcome-form";
import type { Outcome } from "@/lib/outcome-types";

interface Props {
  outcome: Outcome;
  onUpdated: (outcome: Outcome) => void;
}

type Status = "idle" | "saving" | "error";

function Stat({
  label,
  value,
  testid,
}: {
  label: string;
  value: string;
  testid?: string;
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular-nums" data-testid={testid}>
        {value}
      </dd>
    </div>
  );
}

export function OutcomeRow({ outcome, onUpdated }: Props) {
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<OutcomeFormValues>(() =>
    outcomeToFormValues(outcome),
  );
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function startEdit() {
    setValues(outcomeToFormValues(outcome));
    setStatus("idle");
    setErrorMsg(null);
    setEditing(true);
  }

  function cancel() {
    setStatus("idle");
    setErrorMsg(null);
    setEditing(false);
  }

  async function save() {
    setStatus("saving");
    setErrorMsg(null);
    const result = await patchOutcomeAction(
      outcome.id,
      formValuesToPatchInput(values),
    );
    if (result.ok) {
      onUpdated(result.outcome);
      setStatus("idle");
      setEditing(false);
    } else {
      setErrorMsg(result.error);
      setStatus("error");
    }
  }

  if (editing) {
    return (
      <div
        className="space-y-4 rounded-md border border-border p-4"
        data-testid={`outcome-row-${outcome.id}`}
      >
        <OutcomeFields
          idPrefix={outcome.id}
          values={values}
          onChange={(patch) => setValues((v) => ({ ...v, ...patch }))}
          disabled={status === "saving"}
        />
        {status === "error" && (
          <p
            className="text-sm text-destructive"
            data-testid={`row-error-${outcome.id}`}
          >
            {errorMsg}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={cancel}
            disabled={status === "saving"}
          >
            Cancel
          </Button>
          <Button
            type="button"
            data-testid={`row-save-${outcome.id}`}
            onClick={save}
            disabled={status === "saving"}
          >
            {status === "saving" ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-border p-4"
      data-testid={`outcome-row-${outcome.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p
            className="font-mono text-xs text-muted-foreground"
            title={outcome.daily_decision_id}
          >
            decision{" "}
            <span data-testid={`row-decision-${outcome.id}`}>
              {outcome.daily_decision_id.slice(0, 8)}…
            </span>
          </p>
          <p className="text-sm">
            <span className="font-medium">
              {outcome.decision_quality ?? "unrated"}
            </span>
            {" · "}
            {outcome.error_type.replace(/_/g, " ")}
            {" · "}
            {outcome.horizon_days}d
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          data-testid={`row-edit-${outcome.id}`}
          onClick={startEdit}
        >
          Edit
        </Button>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <Stat
          label="Realized"
          value={formatPnl(outcome.pnl_realized)}
          testid={`row-pnl_realized-${outcome.id}`}
        />
        <Stat label="Unrealized" value={formatPnl(outcome.pnl_unrealized)} />
        <Stat label="Regime" value={outcome.actual_regime_realized ?? "—"} />
        <Stat
          label="Match"
          value={
            outcome.regime_match === null
              ? "—"
              : outcome.regime_match
                ? "yes"
                : "no"
          }
        />
      </dl>

      {outcome.notes && (
        <p className="mt-2 text-sm text-muted-foreground">{outcome.notes}</p>
      )}
    </div>
  );
}
