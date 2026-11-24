/**
 * `/sessions/:id` (PRD R4, D7, D14): status timeline derived from the live status doc,
 * gate slots, error cards and delete. The upload, rating card and speaker gate mount in
 * `slots.tsx`.
 */
import { Button } from "@onolys/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { unwrap } from "../../api/client";
import { describeError, failureView } from "../../api/errors";
import type { SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";
import { ACTIONS, H1, LINK, LINK_BTN, NOTE, PAGE } from "../../components/classes";
import { Notice } from "../../components/Notice";
import { formatElapsed, formatResetTime } from "../../lib/format";
import { blockingPeriod, formatBlockingReset } from "../usage/usage";
import { USAGE_KEY, useUsage } from "../usage/useUsage";
import { DeleteDialog } from "./DeleteDialog";
import { ErrorCard } from "./ErrorCard";
import { RetryButton } from "./RetryButton";
import { UploadFailedView } from "./UploadFailedView";
import { RatingCardSlot, SpeakerGateSlot, UploadSlot } from "./slots";
import { deriveTimeline } from "./timeline";
import { useSessionStatus } from "./useSessionStatus";

const NOT_FOUND_MESSAGE = "This upload didn't go through, or the session no longer exists. Start a new upload.";

const STEP_CLASS = {
  done: "border-score-good",
  current: "border-primary font-semibold",
  failed: "border-destructive font-semibold",
  pending: "border-border",
} as const;

export function SessionPage() {
  const { id = "" } = useParams();
  return <SessionView key={id} id={id} />;
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function SessionView({ id }: { id: string }) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const deleting = useRef(false);
  const view = useSessionStatus(id, deleting);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);

  const doc: SessionStatusDoc | null = view.phase === "live" || view.phase === "fallback" ? view.doc : null;
  const runStartedAt = view.phase === "live" ? view.runStartedAt : null;
  const now = useNow(runStartedAt !== null);

  const needsUsage =
    doc !== null && doc.error_code === "daily_cap_reached";
  const usage = useUsage({ enabled: needsUsage });
  const blocking = blockingPeriod(usage.data, "eval");
  const atCap = blocking !== null;
  // A held start (not a real cap) still shows when the day resets.
  const resetsAt = formatBlockingReset(blocking) ?? formatResetTime(usage.data?.eval.day.resets_at);

  // An interview-linked session's first run is free (SP11 R5), so a held first start is not blocked by
  // the eval cap. The status doc is PHI-free and carries no link: ask the session detail, only then.
  const firstStartHeld =
    doc !== null &&
    doc.state === "awaiting_input" &&
    (doc.error_code === "daily_cap_reached" || doc.error_code === "concurrent_runs");
  const detail = useQuery({
    queryKey: ["session-detail", id],
    enabled: firstStartHeld,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}", { params: { path: { id } } })),
  });
  const freeFirstRun = firstStartHeld && Boolean(detail.data?.free_run);

  const run = useMutation({
    mutationFn: async () => unwrap(await client.POST("/sessions/{id}/runs", { params: { path: { id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
    onError: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
  });

  // Retry of a failed step (PRD R6).
  const retry = useMutation({
    mutationFn: async () => unwrap(await client.POST("/sessions/{id}/retry", { params: { path: { id } } })),
  });

  // A successful POST keeps the buttons locked until the status doc moves on (else a second POST races it).
  const { reset: resetRun } = run;
  const docState = doc?.state;
  const { reset: resetRetry } = retry;
  useEffect(() => {
    resetRun();
    resetRetry();
  }, [docState, resetRun, resetRetry]);

  const remove = useMutation({
    mutationFn: async () => {
      deleting.current = true; // the doc vanishing is expected, not an error
      try {
        unwrap(await client.DELETE("/sessions/{id}", { params: { path: { id } } }));
      } catch (e) {
        deleting.current = false;
        throw e;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void navigate("/sessions");
    },
  });

  const closeDialog = () => {
    setConfirmDelete(false);
    remove.reset();
  };

  if (view.phase === "error") {
    return (
      <div className={PAGE}>
        <h1 className={H1}>Session</h1>
        {/* A stale link to a failed upload (session gone, no stub) lands here too (R11). */}
        <ErrorCard
          code={view.error.code}
          message={view.error.code === "not_found" ? NOT_FOUND_MESSAGE : undefined}
          reference={view.error.requestId}
        >
          <Link to="/sessions" className={LINK}>
            Back to your sessions
          </Link>
          {view.error.code === "not_found" ? (
            <Link to="/sessions/new" className={LINK}>
              Start a new upload
            </Link>
          ) : null}
        </ErrorCard>
      </div>
    );
  }

  if (doc && doc.state === "upload_failed") {
    return (
      <div className={PAGE}>
        <h1 className={H1}>Session</h1>
        <UploadFailedView code={doc.error_code} reference={id} />
      </div>
    );
  }

  const timeline = doc ? deriveTimeline(doc, { resetsAt }) : null;
  const failure = doc?.state === "failed" ? failureView(doc) : null;
  const runError = run.error ? describeError(run.error, { resetsAt }) : null;
  const retryError = retry.error ? describeError(retry.error) : null;

  return (
    <div className={PAGE}>
      <h1 className={H1}>Session</h1>

      <div className="grid gap-1 font-semibold" role="status" aria-live="polite">
        {timeline ? timeline.lines.map((l) => <p key={l}>{l}</p>) : <p>Loading session…</p>}
      </div>

      {!doc || !timeline ? null : (
        <>
          {view.phase === "fallback" && view.exhausted ? (
            <Notice role="alert">
              Live updates stopped. This is the latest we could load.{" "}
              <Button type="button" variant="link" className={LINK_BTN} onClick={() => window.location.reload()}>
                Refresh
              </Button>
            </Notice>
          ) : null}

          <ol className="m-0 grid list-none gap-2 p-0" aria-label="Progress">
            {timeline.steps.map((s) => (
              <li key={s.key} data-status={s.status} className={`border-l-4 px-3 py-2 ${STEP_CLASS[s.status]}`}>
                <span>{s.label}</span>{" "}
                <span className="font-normal text-muted-foreground">
                  ({s.status === "done" ? "done" : s.status === "current" ? "in progress" : s.status === "failed" ? "failed" : "not started"})
                </span>
                {s.subLabel ? <span className="font-normal text-muted-foreground"> {s.subLabel}</span> : null}
              </li>
            ))}
          </ol>

          {timeline.showRunCopy ? (
            <>
              <p className={NOTE}>
                Usually under 5 minutes — you can close this tab and come back; your report will be here.
              </p>
              {runStartedAt !== null ? <p className={NOTE}>Elapsed {formatElapsed(now - runStartedAt)}</p> : null}
              {doc.progress > 0 ? (
                <p className={NOTE}>
                  <progress max={100} value={doc.progress} aria-label="Progress" /> {doc.progress}%
                </p>
              ) : null}
            </>
          ) : null}

          {timeline.capReached ? (
            <div>
              <Button
                type="button"
                disabled={run.isPending || run.isSuccess || (atCap && !freeFirstRun)}
                onClick={() => run.mutate()}
              >
                Start
              </Button>
            </div>
          ) : null}

          {doc.state === "report_ready" && doc.latest_report_version !== null ? (
            <div>
              <Button asChild>
                <Link to={`/sessions/${id}/reports/${doc.latest_report_version}`}>View report</Link>
              </Button>
            </div>
          ) : null}

          {failure ? (
            <ErrorCard code={doc.error_code ?? undefined} message={failure.message} note={failure.note} reference={id}>
              {failure.action === "retry" ? (
                <RetryButton pending={retry.isPending || retry.isSuccess} onRetry={() => retry.mutate()} />
              ) : failure.action === "upload_different" ? (
                <Button asChild>
                  <Link to={`/sessions/new?from=${encodeURIComponent(id)}`}>Upload a different file</Link>
                </Button>
              ) : (
                <Button asChild>
                  <Link to="/sessions/new">Start a new session</Link>
                </Button>
              )}
            </ErrorCard>
          ) : null}

          {retryError ? <ErrorCard code={retryError.code} reference={retryError.requestId} /> : null}
          {runError ? <ErrorCard code={runError.code} reference={runError.requestId} resetsAt={resetsAt} /> : null}

          {doc.state === "created" || doc.state === "uploading" || doc.state === "upload_incomplete" ? <UploadSlot sessionId={id} doc={doc} /> : null}
          {doc.state !== "deleting" ? <RatingCardSlot sessionId={id} doc={doc} readOnly={doc.rating_submitted || doc.state === "report_ready"} /> : null}
          {doc.transcript_ready && doc.state !== "deleting" && (!doc.speaker_confirmed || doc.state === "failed") ? (
            <SpeakerGateSlot sessionId={id} doc={doc} />
          ) : null}

          <div className={ACTIONS}>
            <Button
              ref={deleteButton}
              type="button"
              variant="secondary"
              onClick={() => setConfirmDelete(true)}
            >
              Delete session
            </Button>
          </div>
        </>
      )}

      <DeleteDialog open={confirmDelete} busy={remove.isPending} onConfirm={() => remove.mutate()} onCancel={closeDialog}
        onClosed={() => deleteButton.current?.focus()}
      >
        {remove.error ? (
          <ErrorCard
            code={describeError(remove.error).code}
            reference={describeError(remove.error).requestId}
          />
        ) : null}
      </DeleteDialog>
    </div>
  );
}
