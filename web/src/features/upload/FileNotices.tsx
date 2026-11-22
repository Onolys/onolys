import type { FilePick } from "./useFilePick";

/** Block / warning / "Checking file…" under a file input, shared by the form and Resume upload. */
export function FileNotices({ pick }: { pick: FilePick }) {
  return (
    <>
      {pick.checking ? (
        <p className="form-note" aria-live="polite">
          Checking file…
        </p>
      ) : null}
      {pick.check?.blocked ? (
        <p className="form-error" role="alert">
          {pick.check.blocked}
        </p>
      ) : null}
      {pick.check?.warning ? (
        <p className="notice" role="status">
          {pick.check.warning}
        </p>
      ) : null}
    </>
  );
}
