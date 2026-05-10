"use client";

/**
 * Re-exports of Radix Dialog primitives, namespaced to match shadcn/ui's
 * conventions. M0.4 ships only the primitives; styled wrappers (DialogHeader,
 * DialogFooter, etc.) arrive when shadcn add commands run in later milestones.
 *
 * Usage:
 *   import * as Dialog from "@/components/ui/dialog";
 *   <Dialog.Root> <Dialog.Portal> <Dialog.Overlay /> <Dialog.Content /> ...
 */

export {
  Root,
  Trigger,
  Portal,
  Overlay,
  Content,
  Title,
  Description,
  Close,
} from "@radix-ui/react-dialog";
