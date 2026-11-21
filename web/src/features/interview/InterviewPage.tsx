/**
 * `/interviews/:id` (SP10 R8): the live practice interview. Timer from relay events, a warning toast, auto-End
 * at the limit, an End button, a "reconnecting…" state, and a leave prompt (evaluate what I have / discard).
 * After End the recording goes through the ordinary upload path and the session opens with its prefilled goal.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams } from "react-router";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import type { Schemas } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { useApiClient } from "../../auth/useApiClient";
import { Modal } from "../settings/Modal";
import { ErrorCard } from "../session/ErrorCard";
import { prepareUpload } from "../upload/startUpload";
import { getJob } from "../upload/uploader";
import { USAGE_KEY } from "../usage/useUsage";
import { createAudioEngine, type AudioEngine } from "./audio/engine";
import { clock, recordingFile } from "./capText";
import { createLiveController, type LiveController, type LiveState } from "./live/controller";

type Interview = Schemas["InterviewResponse"];

const LOST: Record<string, string> = {
  connection_lost: "We lost the connection and couldn't get it back. You can still evaluate what was recorded, or discard it.",
  signed_out: "Your sign-in expired. You can still evaluate what was recorded, or discard it.",
  not_found: "This interview could not be found.",
  not_live: "This interview is no longer live.",
  relay_error: "Something went wrong with the interview connection.",
};

export function InterviewPage() {
  const { id = "" } = useParams();
  return <InterviewView key={id} id={id} />;
}

function useLive(ctl: LiveController | null): LiveState | null {
  return useSyncExternalStore(
    (fn) => (ctl ? ctl.subscribe(fn) : () => undefined),
    () => (ctl ? ctl.getState() : null),
  );
}

function useTick(active: boolean): void {
  const [, set] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => set((n) => n + 1), 500);
    return () => clearInterval(t);
  }, [active]);
}

function InterviewView({ id }: { id: string }) {
  const client = useApiClient();
  const { service } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const fromPicker = (location.state as { interview?: Interview } | null)?.interview;

  const interview = useQuery({
    queryKey: ["interview", id],
    initialData: fromPicker && fromPicker.interview_id === id ? fromPicker : undefined,
    queryFn: async () => unwrap(await client.GET("/interviews/{id}", { params: { path: { id } } })),
  });

  const engineRef = useRef<AudioEngine | null>(null);
  const ctlRef = useRef<LiveController | null>(null);
  const [ctl, setCtl] = useState<LiveController | null>(null);
  const [micError, setMicError] = useState(false);
  const live = useLive(ctl);
  useTick(live?.phase === "live" || live?.phase === "reconnecting");

  const finishing = useRef(false);
  const leaving = useRef(false);
  const blob = useRef<Blob | null>(null);
  const sessionId = useRef<string | null>(null);

  const active = live !== null && live.phase !== "idle";
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => !leaving.current && active && currentLocation.pathname !== nextLocation.pathname,
  );

  // Tear down when the page goes away: socket closed, mic released.
  useEffect(
    () => () => {
      ctlRef.current?.dispose();
      engineRef.current?.close();
    },
    [],
  );
  // Closing the tab mid-interview loses the recording: ask first.
  useEffect(() => {
    if (!active || leaving.current) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [active]);

  const begin = async () => {
    setMicError(false);
    const engine = createAudioEngine({ onCaptureFrame: (f) => ctlRef.current?.sendFrame(f) });
    try {
      await engine.start(); // a user gesture: mic + audio context
    } catch {
      engine.close();
      setMicError(true);
      return;
    }
    engineRef.current = engine;
    const c = createLiveController({
      url: interview.data?.voice_url ?? "",
      getToken: () => service.getToken(),
      engine,
      limits: interview.data?.limits ? { maxS: interview.data.limits.max_s, warnS: interview.data.limits.warn_s } : undefined,
    });
    ctlRef.current = c;
    setCtl(c);
    c.start();
  };

  const finish = useMutation({
    mutationFn: async () => {
      await ctlRef.current?.requestEnd();
      blob.current ??= await (engineRef.current as AudioEngine).stopRecording();
      engineRef.current?.close();
      unwrap(await client.POST("/interviews/{id}/end", { params: { path: { id } }, body: { discard: false } }));
      sessionId.current ??= unwrap(await client.POST("/sessions", { body: { interview_id: id } })).session.id;
      await prepareUpload(client, sessionId.current, recordingFile(blob.current));
      return sessionId.current;
    },
    onSuccess: (sid) => {
      leaving.current = true;
      void queryClient.invalidateQueries({ queryKey: USAGE_KEY });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void getJob(sid)?.start();
      if (blocker.state === "blocked") blocker.reset();
      void navigate(`/sessions/${sid}`);
    },
    onError: () => {
      finishing.current = false;
    },
  });

  const discard = useMutation({
    mutationFn: async () => {
      unwrap(await client.POST("/interviews/{id}/end", { params: { path: { id } }, body: { discard: true } }));
      ctlRef.current?.dispose();
      engineRef.current?.close();
    },
    onSuccess: () => {
      leaving.current = true;
      void queryClient.invalidateQueries({ queryKey: USAGE_KEY });
      if (blocker.state === "blocked") blocker.proceed();
      else void navigate("/");
    },
  });

  const evaluate = () => {
    if (finishing.current) return;
    finishing.current = true;
    finish.mutate();
  };

  // The relay ended it (time up): wrap up without a click.
  const phase = live?.phase;
  const timeUp = live?.timeUp ?? false;
  useEffect(() => {
    if (phase === "ended" && timeUp && !finishing.current && !discard.isPending && !discard.isSuccess) {
      finishing.current = true;
      finish.mutate();
    }
  }, [phase, timeUp, finish, discard.isPending, discard.isSuccess]);

  if (interview.isPending) return <><h1>Interview</h1><p className="form-note">Loading…</p></>;
  if (interview.isError) {
    const e = describeError(interview.error);
    return (
      <>
        <h1>Interview</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <Link to="/">Back to your sessions</Link>
        </ErrorCard>
      </>
    );
  }
  const iv = interview.data;
  const joinable = iv.state === "created" || iv.state === "live";
  if (!joinable && !active) {
    return (
      <>
        <h1>{iv.scenario.title}</h1>
        <p className="notice">This interview has ended.</p>
        <p>
          <Link to="/">Back to your sessions</Link>
        </p>
      </>
    );
  }

  const busy = finish.isPending || discard.isPending;
  const elapsed = ctl?.elapsed() ?? 0;
  const maxS = live?.maxS ?? iv.limits.max_s;
  const err = finish.error ?? discard.error;
  const e = err ? describeError(err) : null;
  const minutesLeft = live ? Math.max(1, Math.round((live.maxS - live.warnS) / 60)) : 2;

  return (
    <>
      <h1>{iv.scenario.title}</h1>
      <p className="form-note">{iv.scenario.summary}</p>

      {!active ? (
        <>
          <p className="notice">Use headphones. You'll be asked for your microphone, then the client greets you.</p>
          {micError ? (
            <p role="alert" className="form-error">
              We couldn't use your microphone. Allow it in your browser's site settings and try again.
            </p>
          ) : null}
          <p>
            <button type="button" className="btn btn-primary" onClick={() => void begin()}>
              Start talking
            </button>{" "}
            <Link to="/">Not now</Link>
          </p>
        </>
      ) : (
        <>
          <p className="interview-timer" aria-label="Elapsed time">
            <span>{clock(elapsed)}</span> / <span>{clock(maxS)}</span>
          </p>
          <div role="status" aria-live="polite">
            {live?.phase === "connecting" ? <p>Connecting…</p> : null}
            {live?.phase === "reconnecting" ? <p className="notice">Reconnecting… keep talking, your recording continues.</p> : null}
            {live?.phase === "live" ? <p className="form-note">{live.aiSpeaking ? "The client is speaking" : "Listening"}</p> : null}
            {live?.timeUp ? <p>Time's up. Wrapping up…</p> : null}
            {live?.warned && !live.timeUp ? (
              <p className="notice" data-testid="warn-toast">
                {minutesLeft} minute{minutesLeft === 1 ? "" : "s"} left. The interview ends automatically at {clock(live.maxS)}.
              </p>
            ) : null}
            {finish.isPending ? <p>Saving your recording…</p> : null}
          </div>
          {live?.phase === "error" ? (
            <p className="notice" role="alert">
              {LOST[live.errorCode ?? "relay_error"] ?? LOST.relay_error}
            </p>
          ) : null}
          {e ? <ErrorCard code={e.code} reference={e.requestId} /> : null}
          <p>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={evaluate}>
              {finish.isError ? "Try again" : "End interview"}
            </button>{" "}
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => discard.mutate()}>
              Discard
            </button>
          </p>
        </>
      )}

      {blocker.state === "blocked" ? (
        <Modal titleId="leave-title" onEscape={() => blocker.reset()} testId="leave-dialog">
          <h2 id="leave-title">Leave this interview?</h2>
          <p>Your recording is only on this device until it is uploaded.</p>
          <p>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={evaluate}>
              Evaluate what I have
            </button>{" "}
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => discard.mutate()}>
              Discard
            </button>{" "}
            <button type="button" className="link-button" disabled={busy} onClick={() => blocker.reset()}>
              Keep talking
            </button>
          </p>
        </Modal>
      ) : null}
    </>
  );
}
