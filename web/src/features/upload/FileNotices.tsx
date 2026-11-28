import { ErrorNote, Notice, NOTE } from "@onolys/common";
import type { FilePick } from "./useFilePick";

/** Block / warning / "Checking file…" under a file input, shared by the form and Resume upload. */
export function FileNotices({ pick }: { pick: FilePick }) {
  return (
    <>
      {pick.checking ? (
        <p className={NOTE} aria-live="polite">
          Checking file…
        </p>
      ) : null}
      {pick.check?.blocked ? <ErrorNote role="alert">{pick.check.blocked}</ErrorNote> : null}
      {pick.check?.warning ? <Notice role="status">{pick.check.warning}</Notice> : null}
    </>
  );
}
