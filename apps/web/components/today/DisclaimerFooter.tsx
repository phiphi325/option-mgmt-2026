/**
 * Persistent disclaimer footer shown on every page (per plan v1.2 §15).
 *
 * The disclaimer is also injected into every DailyDecision payload (M1.x) so
 * API consumers see it too — the footer is the user-facing surface.
 */
export function DisclaimerFooter() {
  return (
    <footer
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background/85 px-4 py-1.5 text-center text-[11px] text-muted-foreground backdrop-blur-sm"
      role="contentinfo"
    >
      Educational only · Not financial advice · Verify with broker and advisor ·
      Data may be delayed or inaccurate
    </footer>
  );
}
