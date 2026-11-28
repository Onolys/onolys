import type { ReactNode } from "react";
import { ConfirmDialog } from "./ConfirmDialog";

/**
 * Confirm dialog for permanent deletion: a thin wrapper over `ConfirmDialog`.
 * The caller owns the open state and returns focus to the opener.
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
    <ConfirmDialog
      open={open}
      busy={busy}
      slot="delete-dialog"
      title="Delete this session?"
      description="This permanently removes the audio, transcript, rating and all report versions. This can't be undone."
      confirmLabel="Delete permanently"
      confirmVariant="destructive"
      onConfirm={onConfirm}
      onCancel={onCancel}
      onClosed={onClosed}
    >
      {children}
    </ConfirmDialog>
  );
}
