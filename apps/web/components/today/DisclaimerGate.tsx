"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";

const STORAGE_KEY = "disclaimerAcceptedAt_v1";

/**
 * First-run modal that gates the app per plan v1.2 §15 (Disclaimer enforcement)
 * and §22.6 (C5: disclaimer_accepted_at column).
 *
 * Behavior:
 *  - On first visit, modal blocks access until the user clicks "I understand".
 *  - Acceptance is persisted to localStorage in M0.4 (single-user MVP).
 *  - M1.x replaces localStorage with the `users.disclaimer_accepted_at`
 *    DB column (already present in the M0.2 schema).
 *
 * The modal cannot be dismissed via ESC or click-outside — the user must
 * actively confirm. Per plan §3, this is a hard gate.
 */
export function DisclaimerGate({ children }: { children: React.ReactNode }) {
  // null = not yet read from storage (avoids hydration flash); boolean = real value.
  const [accepted, setAccepted] = useState<boolean | null>(null);

  useEffect(() => {
    try {
      setAccepted(localStorage.getItem(STORAGE_KEY) !== null);
    } catch {
      // localStorage may be unavailable (Safari private mode etc.).
      // Fail open: don't block the app.
      setAccepted(true);
    }
  }, []);

  const accept = () => {
    try {
      localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    } catch {
      // ignore — accepted in-memory at least for this session
    }
    setAccepted(true);
  };

  // Render nothing until we know the state; eliminates SSR/CSR hydration flash.
  if (accepted === null) return null;

  return (
    <>
      {children}
      <Dialog.Root open={!accepted}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-fade-in" />
          <Dialog.Content
            className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-xl animate-fade-in"
            onEscapeKeyDown={(e) => e.preventDefault()}
            onPointerDownOutside={(e) => e.preventDefault()}
            onInteractOutside={(e) => e.preventDefault()}
          >
            <Dialog.Title className="text-lg font-semibold">
              Educational use only — please confirm
            </Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-muted-foreground">
              This tool provides decision-support and education about options
              strategies. It is <strong>not</strong> financial advice. Options
              involve substantial risk, including loss of principal.
            </Dialog.Description>

            <div className="mt-4 space-y-2 text-sm">
              <p>By continuing you confirm you understand:</p>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>This is educational, not advice.</li>
                <li>Options carry substantial risk.</li>
                <li>You will verify with a licensed advisor and broker.</li>
                <li>Data shown may be delayed or inaccurate.</li>
                <li>No outcome is guaranteed.</li>
              </ul>
            </div>

            <button
              type="button"
              onClick={accept}
              className="mt-6 w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              I understand — continue
            </button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
