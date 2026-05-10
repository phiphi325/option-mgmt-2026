import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Minimal Button component. Intentionally simpler than shadcn's CVA-based
 * variant in M0.4 — when the Today screen needs richer buttons in M1.x we run
 * `pnpm dlx shadcn@latest add button` to generate the full variant set.
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive";
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
  default:
    "bg-primary text-primary-foreground hover:bg-primary/90",
  outline:
    "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
  ghost:
    "hover:bg-accent hover:text-accent-foreground",
  destructive:
    "bg-destructive text-destructive-foreground hover:bg-destructive/90",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:pointer-events-none disabled:opacity-50",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
