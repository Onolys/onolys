/** Upload progress, cancel, "Retry upload" and "Resume upload" on the session page (PRD R3, D4). */
import { useMutation } from "@tanstack/react-query";
import { useRef, useSyncExternalStore } from "react";
import { describeError } from "../../api/errors";
import type { SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";
import { ErrorCard } from "../session/ErrorCard";
import { FileNotices } from "./FileNotices";
import { prepareUpload } from "./startUpload";
import { getJob, subscribeRegistry, type UploadJob } from "./uploader";
import { useFilePick } from "./useFilePick";

const NO_STATE = { phase: "idle", loaded: 0, total: 0, attempt: 0 } as const;
const mb = (n: number) => (n / (1024 * 1024)).toFixed(1);

function useJob(sessionId: string): UploadJob | undefined {
  return useSyncExternalStore(subscribeRegistry, () => getJob(sessionId));
}

/** Never-uploaded session: pick the file again, get a fresh URL, upload, complete. */
function ResumeUpload({ sessionId }: { sessionId: string }) {
  const client = useApiClient();
  const filePick = useFilePick();
  const busy = useRef(false); // sync guard: a double-click must not request two URLs
  const resume = useMutation({
    mutationFn: async (f: File) => {
      await prepareUpload(client, sessionId, f);
      void getJob(sessionId)?.start();
    },
    onError: () => {
      busy.current = false;
    },
  });
  const err = resume.error ? describeError(resume.error) : null;
  return (
    <>
      <label>
        Audio recording
        <input
          type="file"
          accept=".mp3,.wav,.m4a,.webm,.ogg,audio/*"
          onChange={(e) => void filePick.pick(e.target.files?.[0])}
        />
      </label>
      <FileNotices pick={filePick} />
      {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
      <button
        type="button"
        className="btn btn-primary"
        disabled={!filePick.ready || resume.isPending}
        onClick={() => {
          if (!filePick.file || busy.current) return;
          busy.current = true;
          resume.mutate(filePick.file);
        }}
      >
        {resume.isPending ? "Resuming…" : "Resume upload"}
      </button>
    </>
  );
}

export function UploadSlot({ sessionId, doc }: { sessionId: string; doc: SessionStatusDoc }) {
  const job = useJob(sessionId);
  const state = useSyncExternalStore(
    (fn) => (job ? job.subscribe(fn) : () => undefined),
    () => (job ? job.getState() : NO_STATE),
  );

  const running = job !== undefined && (state.phase === "uploading" || state.phase === "completing");
  if (doc.state === "upload_incomplete" && !running) {
    return (
      <div data-slot="upload" data-session={sessionId}>
        <p className="notice">Pick the same recording again to resume the upload.</p>
        <ResumeUpload sessionId={sessionId} />
      </div>
    );
  }
  if (!job) {
    return (
      <div data-slot="upload" data-session={sessionId}>
        <p className="notice">
          This upload isn't running in this tab. Start a new session to upload the file again.
        </p>
      </div>
    );
  }

  const pct = state.total > 0 ? Math.min(100, Math.round((state.loaded / state.total) * 100)) : 0;
  return (
    <div data-slot="upload" data-session={sessionId}>
      {state.phase === "uploading" || state.phase === "completing" ? (
        <>
          <p>
            <progress max={100} value={pct} aria-label="Upload progress" /> {mb(state.loaded)} of{" "}
            {mb(state.total)} MB ({pct}%)
          </p>
          {state.attempt > 0 ? <p className="form-note">Trying again…</p> : null}
          {state.phase === "uploading" ? (
            <button type="button" className="btn btn-secondary" onClick={() => job.cancel()}>
              Cancel upload
            </button>
          ) : null}
        </>
      ) : null}
      {state.phase === "done" ? <p className="form-note">Upload finished.</p> : null}
      {state.phase === "failed" || state.phase === "cancelled" ? (
        <>
          <p className="form-error" role="alert">
            {state.phase === "cancelled" ? "Upload cancelled." : "The upload didn't finish."}
          </p>
          <button type="button" className="btn btn-primary" onClick={() => void job.retry()}>
            Retry upload
          </button>
        </>
      ) : null}
    </div>
  );
}
