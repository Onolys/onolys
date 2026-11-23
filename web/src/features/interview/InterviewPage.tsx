/**
 * `/interviews/:id` (SP10 R8): the live practice interview. Timer from relay events, a warning toast, auto-End
 * at the limit, an End button, a "reconnecting…" state, and a leave prompt (evaluate what I have / discard).
 * After End the recording goes through the ordinary upload path and the session opens with its prefilled goal.
 */
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Skeleton,
} from "@onolys/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams } from "react-router";
import { unwrap } from "../../api/client";
import { ApiError, describeError } from "../../api/errors";
import type { Schemas } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { useApiClient } from "../../auth/useApiClient";
import { ratingEnabled } from "../../config";
import { ACTIONS, H1, LINK, LINK_BTN, NOTE, PAGE } from "../../components/classes";
import { ErrorNote, Notice } from "../../components/Notice";
import { cardToForm } from "../rating/card";
import { saveGoal } from "../rating/SetupFields";
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
  const goalSaved = useRef(false);

  const active = live !== null && live.phase !== "idle";
  const opener = useRef<HTMLElement | null>(null); // focused element when the leave prompt opened, for focus return on cancel
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    const block = !leaving.current && active && currentLocation.pathname !== nextLocation.pathname;
    const el = document.activeElement;
    if (block && el instanceof HTMLElement && !el.closest('[role="alertdialog"]')) opener.current = el;
    return block;
  });

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

  const [startingUi, setStartingUi] = useState(false);
  const starting = useRef(false); // a second "Start talking" must not make a second engine/mic/socket
  const begin = async () => {
    if (starting.current) return;
    starting.current = true;
    setStartingUi(true);
    setMicError(false);
    const engine = createAudioEngine({ onCaptureFrame: (f) => ctlRef.current?.sendFrame(f) });
    try {
      await engine.start(); // a user gesture: mic + audio context
    } catch {
      engine.close();
      starting.current = false;
      setStartingUi(false);
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
      if (!ratingEnabled() && !goalSaved.current) {
        // D3c: the goal is the scenario's seeded draft; set it so the first run can start.
        const data = unwrap(await client.GET("/sessions/{id}/rating", { params: { path: { id: sessionId.current } } }));
        const goal = cardToForm(data.draft?.card ?? data.final?.card).changeGoal;
        if (goal.trim()) {
          try {
            await saveGoal(client, sessionId.current, goal);
          } catch (e) {
            // 422: leave the goal unset; the session page shows the setup form while unsubmitted.
            if (!(e instanceof ApiError && e.code === "rating_invalid")) throw e;
          }
        } // else: no draft goal, the session page shows the fallback form
        goalSaved.current = true;
      }
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
      else void navigate("/sessions");
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

  // Owner rule D6: leaving ends the interview. A live interview found on page load was left earlier: no rejoin.
  const staleLive = interview.data?.state === "live" && !startingUi && !active;
  const endedStale = useRef(false);
  const [wasStale, setWasStale] = useState(false);
  useEffect(() => {
    if (!staleLive || endedStale.current) return;
    endedStale.current = true;
    setWasStale(true);
    void client.POST("/interviews/{id}/end", { params: { path: { id } }, body: { discard: false } }).then(() => {
      void queryClient.invalidateQueries({ queryKey: USAGE_KEY });
    });
  }, [staleLive, client, id, queryClient]);

  if (interview.isPending)
    return (
      <div className={PAGE} aria-busy="true">
        <h1 className={H1}>Interview</h1>
        <p className={NOTE}>Loading…</p>
        <Skeleton className="h-16 w-full max-w-xl" />
      </div>
    );
  if (interview.isError) {
    const e = describeError(interview.error);
    return (
      <div className={PAGE}>
        <h1 className={H1}>Interview</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <Link to="/sessions" className={LINK}>
            Back to your sessions
          </Link>
        </ErrorCard>
      </div>
    );
  }
  const iv = interview.data;
  const joinable = iv.state === "created";
  if (!joinable && !active) {
    return (
      <div className={PAGE}>
        <h1 className={H1}>{iv.scenario.title}</h1>
        <Notice>{iv.state === "live" || wasStale ? "Interview ended" : "This interview has ended."}</Notice>
        {iv.state === "live" || wasStale ? <p className={NOTE}>You left this interview, so it was ended. Start a new one to practise again.</p> : null}
        <p>
          <Link to="/sessions" className={LINK}>
            Back to your sessions
          </Link>
        </p>
      </div>
    );
  }

  const busy = finish.isPending || discard.isPending;
  const elapsed = ctl?.elapsed() ?? 0;
  const maxS = live?.maxS ?? iv.limits.max_s;
  const err = finish.error ?? discard.error;
  const e = err ? describeError(err) : null;
  const minutesLeft = live ? Math.max(1, Math.round((live.maxS - live.warnS) / 60)) : 2;

  return (
    <div className={PAGE}>
      <h1 className={H1}>{iv.scenario.title}</h1>
      <p className={NOTE}>{iv.scenario.summary}</p>

      {!active ? (
        <>
          <Notice>Use headphones. You'll be asked for your microphone, then the client greets you.</Notice>
          {micError ? (
            <ErrorNote role="alert">We couldn't use your microphone. Allow it in your browser's site settings and try again.</ErrorNote>
          ) : null}
          <div className={ACTIONS}>
            <Button type="button" disabled={startingUi} onClick={() => void begin()}>
              Start talking
            </Button>
            <Link to="/new" className={LINK}>
              Not now
            </Link>
          </div>
        </>
      ) : (
        <>
          <p className="text-2xl tabular-nums" aria-label="Elapsed time">
            <span>{clock(elapsed)}</span> / <span>{clock(maxS)}</span>
          </p>
          <div role="status" aria-live="polite" className="grid gap-3 empty:hidden">
            {live?.phase === "connecting" ? <p>Connecting…</p> : null}
            {live?.phase === "reconnecting" ? <Notice>Reconnecting… keep talking, your recording continues.</Notice> : null}
            {live?.phase === "live" ? <p className={NOTE}>{live.aiSpeaking ? "The client is speaking" : "Listening"}</p> : null}
            {live?.timeUp ? <p>Time's up. Wrapping up…</p> : null}
            {live?.phase === "ended" && !live.timeUp && !finish.isPending ? (
              <Notice>The interview has ended. Use End interview to save your recording, or Discard.</Notice>
            ) : null}
            {live?.warned && !live.timeUp ? (
              <Notice data-testid="warn-toast">
                {minutesLeft} minute{minutesLeft === 1 ? "" : "s"} left. The interview ends automatically at {clock(live.maxS)}.
              </Notice>
            ) : null}
            {finish.isPending ? <p>Saving your recording…</p> : null}
          </div>
          {live?.phase === "error" ? <Notice role="alert">{LOST[live.errorCode ?? "relay_error"] ?? LOST.relay_error}</Notice> : null}
          {e ? <ErrorCard code={e.code} reference={e.requestId} /> : null}
          <div className={ACTIONS}>
            <Button type="button" disabled={busy} onClick={evaluate}>
              {finish.isError ? "Try again" : "End interview"}
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => discard.mutate()}>
              Discard
            </Button>
          </div>
        </>
      )}

      <AlertDialog
        open={blocker.state === "blocked"}
        onOpenChange={(next) => {
          if (!next && !busy && blocker.state === "blocked") blocker.reset();
        }}
      >
        <AlertDialogContent
          data-testid="leave-dialog"
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            // Leaving: the next page's heading takes focus. Staying: back to where the user was.
            if (!leaving.current && opener.current?.isConnected) opener.current.focus();
          }}
          onEscapeKeyDown={(e) => {
            if (busy) e.preventDefault();
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>Leave this interview?</AlertDialogTitle>
            <AlertDialogDescription>Your recording is only on this device until it is uploaded.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button type="button" disabled={busy} onClick={evaluate}>
              Evaluate what I have
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => discard.mutate()}>
              Discard
            </Button>
            <AlertDialogCancel variant="link" className={LINK_BTN} disabled={busy}>
              Keep talking
            </AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
