import { Button, LINK_BTN } from "@onolys/common";
import { useCodedDialog } from "./codedDialogContext";

/** Button showing an utterance number; opens the coded transcript at that row. */
export function UtteranceLink({ n, bracketed = false }: { n: number; bracketed?: boolean }) {
  const { open } = useCodedDialog();
  return (
    <Button
      type="button"
      variant="link"
      className={`${LINK_BTN} inline h-auto min-h-0 min-w-0 py-0 align-baseline`}
      aria-label={`Open utterance ${n}`}
      onClick={() => open(n)}
    >
      {bracketed ? `[${n}]` : n}
    </Button>
  );
}
