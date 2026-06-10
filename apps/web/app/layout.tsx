import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { DisclaimerGate } from "@/components/today/DisclaimerGate";
import { DisclaimerFooter } from "@/components/today/DisclaimerFooter";

export const metadata: Metadata = {
  title: "Option Mgmt — MSFT Risk Management Engine",
  description:
    "Educational decision-support for a long-term MSFT holder. Not financial advice.",
};

/**
 * Minimal Phase-1 top navigation (M1.22). Two surfaces ship in Phase 1 —
 * Today and Settings; Outcomes lands with M1.23. Static links (no active-state
 * styling) keep this a server component. The exact nav chrome is intentionally
 * lightweight per the M1.22 spec ("exact nav chrome is implementation detail").
 */
function SiteHeader() {
  return (
    <header className="border-b border-border">
      <nav className="container mx-auto flex items-center gap-6 px-4 py-3 text-sm">
        <Link href="/today" className="font-semibold tracking-tight">
          Option Mgmt
        </Link>
        <div className="flex items-center gap-4 text-muted-foreground">
          <Link href="/today" className="transition-colors hover:text-foreground">
            Today
          </Link>
          <Link
            href="/settings"
            className="transition-colors hover:text-foreground"
          >
            Settings
          </Link>
        </div>
      </nav>
    </header>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground">
        <DisclaimerGate>
          <SiteHeader />
          {children}
        </DisclaimerGate>
        <DisclaimerFooter />
      </body>
    </html>
  );
}
