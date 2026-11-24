import { useRef, useState } from "react";
import { LINK } from "../../components/classes";
import { ConfirmDialog } from "./ConfirmDialog";

const CANCELLABLE = new Set(["created", "uploading", "upload_incomplete", "validating", "transcribing", "awaiting_input", "running"]);

/** The seven in-progress states a session can be cancelled from (04-cancel R1, R9). */
export function isCancellable(state: string | null | undefined): boolean {
  return state != null && CANCELLABLE.has(state);
}

// Variant A: nothing was spent yet. Variant B: transcription has started (04-cancel R9, D7).
const EARLY = new Set(["created", "uploading", "upload_incomplete", "validating"]);
const COPY_A = "Processing stops. Your upload stays until you delete the session. This won't count toward your limit.";
const COPY_B = "Processing stops. Transcription has started, so this counts toward your daily limit.";

/**
 * Quiet blue link (red on hover) that opens the confirm dialog. After confirming the dialog closes and the
 * link reads `Cancelling…` with a spinner, `aria-busy` and disabled until the POST returns (`pending`).
 * Renders nothing outside the seven cancellable states. `freeRun` (interview-linked) always gets variant A.
 */
export function CancelLink({
  state,
  freeRun = false,
  pending,
  onConfirm,
  onOpen,
}: {
  state: string;
  freeRun?: boolean;
  pending: boolean;
  onConfirm: () => void;
  /** Runs when the dialog opens (the page may load the session detail for `freeRun`). */
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const link = useRef<HTMLButtonElement>(null);
  if (!isCancellable(state)) return null;
  const variantA = EARLY.has(state) || freeRun;
  return (
    <>
      <button
        ref={link}
        type="button"
        className={`${LINK} bg-transparent p-0 hover:text-destructive disabled:cursor-wait disabled:no-underline disabled:opacity-70`}
        disabled={pending}
        aria-busy={pending}
        onClick={() => {
          onOpen?.();
          setOpen(true);
        }}
      >
        {pending ? (
          <>
            <span
              data-slot="spinner"
              aria-hidden="true"
              className="mr-2 inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent align-[-1px]"
            />
            Cancelling…
          </>
        ) : (
          "Cancel session"
        )}
      </button>
      <ConfirmDialog
        open={open}
        busy={false}
        slot="cancel-dialog"
        title="Cancel this session?"
        description={variantA ? COPY_A : COPY_B}
        confirmLabel="Cancel session"
        confirmVariant="default"
        cancelLabel="Keep processing"
        onConfirm={() => {
          setOpen(false);
          onConfirm();
        }}
        onCancel={() => setOpen(false)}
        onClosed={() => link.current?.focus()}
      />
    </>
  );
}
