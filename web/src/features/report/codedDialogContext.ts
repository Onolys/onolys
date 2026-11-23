import { createContext, useContext } from "react";

export interface CodedDialogApi {
  /** Open the coded transcript, scrolled to utterance `n` (1-based) when given. */
  open: (n?: number) => void;
}

/** Default is a no-op: the dialog itself is provided by an ancestor (SP2 Task 4). */
export const CodedDialogContext = createContext<CodedDialogApi>({ open: () => {} });

export const useCodedDialog = (): CodedDialogApi => useContext(CodedDialogContext);
