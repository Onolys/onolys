import { Button } from "@onolys/ui";
import { LINK_BTN } from "../../components/classes";
import { useCodedDialog } from "./codedDialogContext";

/** Button showing an utterance number; opens the coded transcript at that row. */
export function UtteranceLink({ n }: { n: number }) {
  const { open } = useCodedDialog();
  return (
    <Button
      type="button"
      variant="link"
      className={`${LINK_BTN} inline h-auto min-h-0 min-w-0 py-0 align-baseline`}
      aria-label={`Open utterance ${n}`}
      onClick={() => open(n)}
    >
      {n}
    </Button>
  );
}
