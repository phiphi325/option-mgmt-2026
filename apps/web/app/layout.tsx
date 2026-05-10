import type { Metadata } from "next";
import "./globals.css";
import { DisclaimerGate } from "@/components/today/DisclaimerGate";
import { DisclaimerFooter } from "@/components/today/DisclaimerFooter";

export const metadata: Metadata = {
  title: "Option Mgmt — MSFT Risk Management Engine",
  description:
    "Educational decision-support for a long-term MSFT holder. Not financial advice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground">
        <DisclaimerGate>{children}</DisclaimerGate>
        <DisclaimerFooter />
      </body>
    </html>
  );
}
