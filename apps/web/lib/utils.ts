import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class strings, with later classes overriding earlier ones
 * for conflicting utilities. Standard shadcn helper — used pervasively in
 * components/ui/*.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
