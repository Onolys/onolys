import { useCodedDialog } from "./codedDialogContext";

/** Button showing an utterance number; opens the coded transcript at that row. */
export function UtteranceLink({ n }: { n: number }) {
  const { open } = useCodedDialog();
  return (
    <button type="button" className="link-button" aria-label={`Open utterance ${n}`} onClick={() => open(n)}>
      {n}
    </button>
  );
}
