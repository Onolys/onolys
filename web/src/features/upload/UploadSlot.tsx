/** Upload progress, cancel, "Retry upload" and "Resume upload" on the session page. */
import { Button, Input } from "@onolys/ui";
import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { describeError } from "../../api/errors";
import type { SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";
import { NOTE } from "../../components/classes";
import { Field } from "../../components/Field";
import { ErrorNote, Notice } from "../../components/Notice";
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
    <div className="grid gap-3">
      <Field label="Audio recording">
        {(id) => (
          <Input
            id={id}
            type="file"
            accept=".mp3,.wav,.m4a,.webm,.ogg,audio/*"
            onChange={(e) => void filePick.pick(e.target.files?.[0])}
          />
        )}
      </Field>
      <FileNotices pick={filePick} />
      {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
      <Button
        type="button"
        className="justify-self-start"
        disabled={!filePick.ready || resume.isPending}
        onClick={() => {
          if (!filePick.file || busy.current) return;
          busy.current = true;
          resume.mutate(filePick.file);
        }}
      >
        {resume.isPending ? "Resuming…" : "Resume upload"}
      </Button>
    </div>
  );
}

/**
 * `onFraction` reports this tab's real byte fraction (0-1) for the overall progress bar,
 * or null when there is no counter (a reload, no job). This component draws no overall bar itself.
 */
export function UploadSlot({
  sessionId,
  doc,
  onFraction,
}: {
  sessionId: string;
  doc: SessionStatusDoc;
  onFraction?: (fraction: number | null) => void;
}) {
  const job = useJob(sessionId);
  // Stable per job: a new function each render would unsubscribe and resubscribe (and evict a finished job).
  const subscribe = useCallback((fn: () => void) => (job ? job.subscribe(fn) : () => undefined), [job]);
  const state = useSyncExternalStore(subscribe, () => (job ? job.getState() : NO_STATE));

  const fraction = job && state.total > 0 ? Math.min(1, state.loaded / state.total) : null;
  useEffect(() => {
    onFraction?.(fraction);
  }, [fraction, onFraction]);

  const running = job !== undefined && (state.phase === "uploading" || state.phase === "completing");
  // No upload running in this tab (stale server state, a reload, a second tab): pick the file again.
  if (!running && (doc.state === "upload_incomplete" || !job)) {
    return (
      <div data-slot="upload" data-session={sessionId} className="grid gap-3">
        <Notice>
          {doc.state === "upload_incomplete"
            ? "Pick the same recording again to resume the upload."
            : "This upload isn't running in this tab. Pick the same recording again to continue it."}
        </Notice>
        <ResumeUpload sessionId={sessionId} />
      </div>
    );
  }
  if (!job) return null;

  const pct = state.total > 0 ? Math.min(100, Math.round((state.loaded / state.total) * 100)) : 0;
  return (
    <div data-slot="upload" data-session={sessionId} className="grid gap-3">
      {state.phase === "uploading" || state.phase === "completing" ? (
        <>
          <p>
            {mb(state.loaded)} of{" "}
            {mb(state.total)} MB ({pct}%)
          </p>
          {state.attempt > 0 ? <p className={NOTE}>Trying again…</p> : null}
          {state.phase === "uploading" ? (
            <Button type="button" variant="outline" className="justify-self-start" onClick={() => job.cancel()}>
              Cancel upload
            </Button>
          ) : null}
        </>
      ) : null}
      {state.phase === "done" ? <p className={NOTE}>Upload finished.</p> : null}
      {state.phase === "failed" || state.phase === "cancelled" ? (
        <>
          <ErrorNote role="alert">{state.phase === "cancelled" ? "Upload cancelled." : (state.error?.message ?? "The upload didn't finish.")}</ErrorNote>
          <Button type="button" className="justify-self-start" onClick={() => void job.retry()}>
            Retry upload
          </Button>
        </>
      ) : null}
    </div>
  );
}
