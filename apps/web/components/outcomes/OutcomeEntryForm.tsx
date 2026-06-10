"use client";

/**
 * Manual outcome entry (M1.23). Creates an outcome tied to a
 * `daily_decision_id` via the `createOutcome` server action, then hands the
 * created row to the parent (`OutcomeTracker`) to prepend to the history.
 *
 * Dependency-free (Path A): native controls + `useState`; the save round-trips
 * through a server action (httpOnly `access_token` cookie). The decision id is
 * an editable field (paste from the Today card footer) — a `?decision_id=`
 * deep-link prefill is a deferred follow-up (see the M1.23 dev spec).
 */

import { type FormEvent, useState } from "react";

import { createOutcomeAction } from "@/app/outcomes/actions";
import { Button } from "@/components/ui/button";
import { OutcomeFields } from "@/components/outcomes/OutcomeFields";
import {
  EMPTY_OUTCOME_FORM,
  type OutcomeFormValues,
  canCreate,
  formValuesToCreateInput,
} from "@/lib/outcome-form";
import type { Outcome } from "@/lib/outcome-types";

interface Props {
  onCreated: (outcome: Outcome) => void;
}

type Status = "idle" | "saving" | "saved" | "error";

export function OutcomeEntryForm({ onCreated }: Props) {
  const [decisionId, setDecisionId] = useState("");
  const [values, setValues] = useState<OutcomeFormValues>(EMPTY_OUTCOME_FORM);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const submittable = canCreate(values, decisionId) && status !== "saving";

  function markDirty() {
    if (status !== "idle") {
      setStatus("idle");
      setErrorMsg(null);
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canCreate(values, decisionId) || status === "saving") return;
    setStatus("saving");
    setErrorMsg(null);
    const result = await createOutcomeAction(
      formValuesToCreateInput(values, decisionId),
    );
    if (result.ok) {
      onCreated(result.outcome);
      setDecisionId("");
      setValues(EMPTY_OUTCOME_FORM);
      setStatus("saved");
    } else {
      setErrorMsg(result.error);
      setStatus("error");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="outcome-entry-form"
      className="space-y-4 rounded-lg border bg-card p-6 shadow-sm"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Record an outcome
      </h2>

      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Decision ID</span>
        <input
          type="text"
          data-testid="field-new-daily_decision_id"
          value={decisionId}
          onChange={(e) => {
            setDecisionId(e.target.value);
            markDirty();
          }}
          placeholder="Paste the decision_id from the Today card footer"
          className="block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <span className="block text-xs text-muted-foreground">
          The UUID of the daily decision this outcome closes. One outcome per
          decision.
        </span>
      </label>

      <OutcomeFields
        idPrefix="new"
        values={values}
        onChange={(patch) => {
          setValues((v) => ({ ...v, ...patch }));
          markDirty();
        }}
        disabled={status === "saving"}
      />

      <div className="flex items-center justify-between gap-3 pt-1">
        <p
          data-testid="entry-status"
          aria-live="polite"
          className={
            status === "error"
              ? "text-sm text-destructive"
              : "text-sm text-muted-foreground"
          }
        >
          {status === "saving" && "Saving…"}
          {status === "saved" && "Outcome recorded."}
          {status === "error" && (errorMsg ?? "Save failed.")}
        </p>
        <Button type="submit" data-testid="entry-save-button" disabled={!submittable}>
          {status === "saving" ? "Saving…" : "Record outcome"}
        </Button>
      </div>
    </form>
  );
}
