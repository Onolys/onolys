import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
} from "@onolys/ui";
import type { ComponentProps, ReactNode } from "react";

/**
 * Reusable confirm dialog: the shared AlertDialog (role alertdialog, focus starts on the cancel
 * button). Escape or the cancel button closes it, but not while a request is in flight (`busy`):
 * its failure must stay visible. The caller owns the open state and returns focus to the opener.
 */
export function ConfirmDialog({
  open,
  busy,
  title,
  description,
  confirmLabel,
  confirmVariant = "destructive",
  cancelLabel = "Cancel",
  slot = "confirm-dialog",
  onConfirm,
  onCancel,
  onClosed,
  children,
}: {
  open: boolean;
  busy: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  confirmVariant?: ComponentProps<typeof Button>["variant"];
  cancelLabel?: string;
  /** `data-slot` of the dialog content. */
  slot?: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Runs after close; the caller returns focus to the opener. */
  onClosed?: () => void;
  /** Error card slot, shown inside the dialog. */
  children?: ReactNode;
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onCancel();
      }}
    >
      <AlertDialogContent
        data-slot={slot}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          onClosed?.();
        }}
        onEscapeKeyDown={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel variant="secondary" disabled={busy}>
            {cancelLabel}
          </AlertDialogCancel>
          <Button type="button" variant={confirmVariant} onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
