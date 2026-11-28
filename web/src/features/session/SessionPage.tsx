/**
 * `/sessions/:id`: status timeline derived from the live status doc,
 * gate slots and error cards. Completed sessions open their report automatically.
 * The upload, rating card and speaker gate mount in
 * `slots.tsx`.
 */
import { Button, Progress, Spinner, H1, LINK, LINK_BTN, NOTE, PAGE, Notice, formatElapsed, formatResetTime } from "@onolys/common";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router";
import { unwrap } from "../../api/client";
import { cancelErrorMessage, describeError, failureView } from "../../api/errors";
import type { SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";
import { codePointLength, sliceCodePoints } from "../report/codepoints";
import { blockingPeriod, formatBlockingReset } from "../usage/usage";
import { USAGE_KEY, useUsage } from "../usage/useUsage";
import { CancelLink, isCancellable } from "./CancelLink";
import { CancelledView } from "./CancelledView";
import { DeleteSession } from "./DeleteSession";
import { ErrorCard } from "./ErrorCard";
import { RetryButton } from "./RetryButton";
import { UploadFailedView } from "./UploadFailedView";
import { RatingCardSlot, SpeakerGateSlot, UploadSlot } from "./slots";
import { deriveTimeline } from "./timeline";
import { useProgress, useSessionStatus } from "./useSessionStatus";

const NOT_FOUND_MESSAGE = "We couldn't find this session. It may have been deleted, or the link may be mistyped.";

const STEP_CLASS = {
  done: "border-score-good text-score-good",
  current: "border-primary text-primary font-semibold",
  failed: "border-destructive text-destructive font-semibold",
  pending: "border-border text-muted-foreground",
} as const;

const STEP_STATUS_TEXT = { done: "Done", current: "In progress", failed: "Failed", pending: "Not started" } as const;

export function SessionPage() {
  const { id = "" } = useParams();
  return <SessionView key={id} id={id} />;
}

function SessionView({ id }: { id: string }) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const quiet = useRef(false);
  const view = useSessionStatus(id, quiet);

  const doc: SessionStatusDoc | null = view.phase === "live" || view.phase === "fallback" ? view.doc : null;
  // This tab's upload byte fraction (UploadSlot), so the bar moves during the upload.
  const [uploadFraction, setUploadFraction] = useState<number | null>(null);
  const progress = useProgress(doc, uploadFraction);

  const needsUsage =
    doc !== null && doc.error_code === "daily_cap_reached";
  const usage = useUsage({ enabled: needsUsage });
  const blocking = blockingPeriod(usage.data, "eval");
  const atCap = blocking !== null;
  // A held start (not a real cap) still shows when the day resets.
  const resetsAt = formatBlockingReset(blocking) ?? formatResetTime(usage.data?.eval.day.resets_at);

  // An interview-linked session's first run is free, so a held first start is not blocked by
  // the eval cap. The status doc is PHI-free; session detail supplies the free-run flag.
  const firstStartHeld =
    doc !== null &&
    doc.state === "awaiting_input" &&
    (doc.error_code === "daily_cap_reached" || doc.error_code === "concurrent_runs");
  const detail = useQuery({
    queryKey: ["session-detail", id],
    // The status document omits session names; load private metadata through the API.
    queryFn: async () => unwrap(await client.GET("/sessions/{id}", { params: { path: { id } } })),
  });
  const rating = useQuery({
    queryKey: ["session-heading-goal", id, doc?.rating_submitted],
    enabled: Boolean(detail.data && !detail.data.title?.trim()),
    retry: false,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}/rating", { params: { path: { id } } })),
  });
  const savedGoal = rating.data?.final?.card?.change_goal ?? rating.data?.draft?.card?.change_goal;
  const goal = typeof savedGoal === "string" ? savedGoal.trim() : "";
  const label = detail.data?.title?.trim() || (goal ? `${sliceCodePoints(goal, 0, 20)}${codePointLength(goal) > 20 ? "…" : ""}` : "");
  const heading = label ? `Session - ${label}` : "Session";
  const freeFirstRun = firstStartHeld && Boolean(detail.data?.free_run);

  // Cancel: idempotent, so a failed POST is safe to retry.
  const cancel = useMutation({
    mutationFn: async () => unwrap(await client.POST("/sessions/{id}/cancel", { params: { path: { id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
  });

  const run = useMutation({
    mutationFn: async () => unwrap(await client.POST("/sessions/{id}/runs", { params: { path: { id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
    onError: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
  });

  // Retry of a failed step.
  const retry = useMutation({
    mutationFn: async () => unwrap(await client.POST("/sessions/{id}/retry", { params: { path: { id } } })),
  });

  // A successful POST keeps the buttons locked until the status doc moves on (else a second POST races it).
  const { reset: resetRun } = run;
  const docState = doc?.state;
  // A merged failed -> failed snapshot keeps the state but changes retries_left: also a move-on.
  const retriesLeft = doc?.retries_left;
  const { reset: resetRetry } = retry;
  useEffect(() => {
    resetRun();
    resetRetry();
  }, [docState, retriesLeft, resetRun, resetRetry]);

  const reportVersion = doc?.latest_report_version ?? detail.data?.latest_report_version;
  if (reportVersion != null) return <Navigate to={`/sessions/${id}/reports/${reportVersion}`} replace />;

  if (view.phase === "error") {
    return (
      <div className={PAGE}>
        <h1 className={H1}>{heading}</h1>
        {/* A failed upload with a stub shows UploadFailedView; a missing session without one is generic not-found. */}
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
              Start a new session
            </Link>
          ) : null}
        </ErrorCard>
      </div>
    );
  }

  if (doc && doc.state === "upload_failed") {
    return (
      <div className={PAGE}>
        <h1 className={H1}>{heading}</h1>
        <UploadFailedView code={doc.error_code} reference={id} />
      </div>
    );
  }

  const cancelled = doc?.state === "cancelled" || cancel.isSuccess;
  const cancelledCounted = doc?.state === "cancelled" ? doc.counted : cancel.data?.counted;
  const timeline = doc ? deriveTimeline(doc, { resetsAt }) : null;
  const failure = doc?.state === "failed" ? failureView(doc) : null;
  const runError = run.error ? describeError(run.error, { resetsAt }) : null;
  const retryError = retry.error ? describeError(retry.error) : null;

  return (
    <div className={PAGE}>
      <h1 className={H1}>{heading}</h1>

      {cancelled ? (
        <>
          <CancelledView counted={cancelledCounted} />
          <DeleteSession id={id} onBusyChange={(busy) => { quiet.current = busy; }} />
        </>
      ) : null}

      {cancelled ? null : <div className="grid gap-1 font-semibold" role="status" aria-live="polite">
        {timeline ? timeline.lines.map((l) => <p key={l}>{l}</p>) : <p>Loading session…</p>}
      </div>}

      {cancelled || !doc || !timeline ? null : (
        <>
          {view.phase === "fallback" && view.exhausted ? (
            <Notice role="alert">
              Live updates stopped. This is the latest we could load.{" "}
              <Button type="button" variant="link" className={LINK_BTN} onClick={() => window.location.reload()}>
                Refresh
              </Button>
            </Notice>
          ) : null}

          {progress && !progress.hidden && doc.state !== "report_ready" ? (
            <div className="grid gap-2">
              <div className="flex items-center gap-3">
                <Progress
                  aria-label="Overall progress"
                  aria-valuetext={`${progress.pct} percent`}
                  value={progress.pct}
                  className="flex-1"
                />
                <span className="text-sm tabular-nums">{progress.pct}%</span>
              </div>
              <p className={NOTE}>Elapsed {formatElapsed(progress.elapsedMs)}</p>
            </div>
          ) : null}

          {timeline.hint ? (
            <p data-slot="hint" className={NOTE}>
              {timeline.hint}
            </p>
          ) : null}

          <ol className="m-0 grid list-none gap-2 p-0" aria-label="Progress">
            {timeline.steps.map((s) => (
              <li
                key={s.key}
                data-status={s.status}
                className={`flex flex-wrap items-center gap-x-2 border-l-4 px-3 py-2 ${STEP_CLASS[s.status]}`}
              >
                {s.status === "done" ? (
                  <span data-slot="step-check" aria-hidden="true">
                    ✓
                  </span>
                ) : s.status === "current" ? (
                  <Spinner />
                ) : null}
                <span>{s.label}</span>
                <span className="font-normal">{STEP_STATUS_TEXT[s.status]}</span>
                {s.subLabel ? <span className="font-normal text-muted-foreground">{s.subLabel}</span> : null}
              </li>
            ))}
          </ol>

          {isCancellable(doc.state) ? (
            <div data-slot="cancel" className="flex justify-end">
              <CancelLink
                state={doc.state}
                freeRun={Boolean(detail.data?.free_run)}
                pending={cancel.isPending}
                onOpen={() => {
                  cancel.reset();
                }}
                onConfirm={() => cancel.mutate()}
              />
            </div>
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
          {failure ? <DeleteSession id={id} onBusyChange={(busy) => { quiet.current = busy; }} /> : null}

          {retryError ? <ErrorCard code={retryError.code} reference={retryError.requestId} /> : null}
          {runError ? <ErrorCard code={runError.code} reference={runError.requestId} resetsAt={resetsAt} /> : null}

          {doc.state === "created" || doc.state === "uploading" || doc.state === "upload_incomplete" ? <UploadSlot sessionId={id} doc={doc} onFraction={setUploadFraction} /> : null}
          {doc.state !== "deleting" ? <RatingCardSlot sessionId={id} doc={doc} readOnly={doc.rating_submitted || doc.state === "running" || doc.state === "failed" || doc.state === "report_ready"} /> : null}
          {doc.transcript_ready && !doc.speaker_confirmed && doc.state === "awaiting_input" ? (
            <SpeakerGateSlot sessionId={id} doc={doc} />
          ) : null}

          {cancel.error ? (
            <ErrorCard message={cancelErrorMessage(cancel.error)} code={undefined} reference={id} />
          ) : null}
        </>
      )}
    </div>
  );
}
