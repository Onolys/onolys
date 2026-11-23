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
import type { ReactNode } from "react";

/**
 * Confirm dialog for permanent deletion (PRD R4 Delete): the shared AlertDialog (role alertdialog,
 * focus starts on Cancel). Escape or Cancel closes it, but not while a delete is in flight: its
 * failure must stay visible. The caller owns the open state and returns focus to the opener.
 */
export function DeleteDialog({
  open,
  busy,
  onConfirm,
  onCancel,
  onClosed,
  children,
}: {
  open: boolean;
  busy: boolean;
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
        data-slot="delete-dialog"
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          onClosed?.();
        }}
        onEscapeKeyDown={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this session?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the audio, transcript, rating and all report versions. This can't be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel variant="secondary" disabled={busy}>
            Cancel
          </AlertDialogCancel>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={busy}>
            Delete permanently
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
