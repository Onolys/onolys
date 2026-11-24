import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { ApiError, describeLookupError, type ErrorDescription } from "../../api/errors";
import { unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { getStatusListener, normalizeStatusDoc, type SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";
import { deriveProgress, isTimedState, isUploadState, type DerivedProgress } from "./progress";

export type StatusView =
  | { phase: "loading" }
  /** Doc from the live listener. */
  | { phase: "live"; doc: SessionStatusDoc; runStartedAt: number | null }
  /**
   * The listener is down; `GET /sessions/{id}` is polled meanwhile. `exhausted`: the resubscribe
   * retries ran out (the poll goes on, but the page tells the user live updates stopped).
   */
  | { phase: "fallback"; doc: SessionStatusDoc; exhausted: boolean }
  /** The fallback GET failed too (404 = unknown or someone else's session). */
  | { phase: "error"; error: ErrorDescription };

type Detail = components["schemas"]["SessionDetail"];

export function detailToDoc(d: Detail): SessionStatusDoc {
  return normalizeStatusDoc({
    ...d.flags,
    uid: "",
    state: d.status,
    step: d.step,
    progress: d.progress,
    error_code: d.error?.code,
    error_kind: d.error_kind,
    retries_left: d.retries_left,
    counted: d.counted,
    latest_report_version: d.latest_report_version,
    updated_at: d.updated_at,
    started_at: d.started_at,
    stage_started_at: d.stage_started_at,
    waited_ms: d.waited_ms,
    audio_s: d.audio_s,
    progress_next: d.progress_next,
    stage_expected_s: d.stage_expected_s,
  });
}

/** A session stuck in `transcribing` this long gets a `GET /sessions/{id}`, which makes the API settle it. */
export const STALE_NUDGE_AFTER_MS = 6 * 60_000;
/**
 * The API settles stuck sessions lazily, on a read (api jobs/stale.py). Per state, how long a stuck session
 * waits before that settles it: uploads = signed-URL lifetime (15 min) + 60 s; validating/running =
 * 2 attempts x (480 s deadline + 60 s lease) + 300 s retry slack. `transcribing` has its own, shorter cap.
 */
export const STALE_NUDGE_AFTER_BY_STATE: Partial<Record<SessionStatusDoc["state"], number>> = {
  created: 16 * 60_000,
  uploading: 16 * 60_000,
  transcribing: STALE_NUDGE_AFTER_MS,
  validating: 23 * 60_000,
  running: 23 * 60_000,
};
/** While it stays in such a state, nudge at most this often. */
export const STALE_NUDGE_EVERY_MS = 60_000;
/** How often a held-back update is checked for release (the `quiet` ref has no change event). */
const QUIET_CHECK_MS = 250;

/** Resubscribe delays after a listener drop (D7); when they run out the page shows "Live updates stopped". */
export const RESUBSCRIBE_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000];
/** While the listener is down, poll the session detail this often. */
export const FALLBACK_POLL_MS = 5_000;

/**
 * Overall progress for a doc, re-derived once a second only while Elapsed or the % can move (timed states, and uploading once started_at is set)
 * (05-processing-screen R3, R8). `uploadFraction` is the uploader's byte fraction, if this tab has one.
 */
export function useProgress(doc: SessionStatusDoc | null, uploadFraction?: number | null): DerivedProgress | null {
  const [now, setNow] = useState(() => Date.now());
  // Elapsed ticks in every state but awaiting_input and the finished/hidden ones (R3); the % only moves in timed states (deriveProgress).
  const timed = doc !== null && (isTimedState(doc.state) || (isUploadState(doc.state) && doc.started_at != null));
  useEffect(() => {
    if (!timed) return;
    const first = setTimeout(() => setNow(Date.now()), 0); // catch up after a pause, not a minute-old `now`
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [timed]);
  return doc ? deriveProgress(doc, now, uploadFraction) : null;
}

type Floor = { state: SessionStatusDoc["state"]; progress: number };

/** The doc with `progress` held at the highest value seen in its state (a late, lower doc cannot move the bar back). */
function keepMax(floor: Floor | null, doc: SessionStatusDoc): [SessionStatusDoc, Floor] {
  const progress = floor && floor.state === doc.state ? Math.max(floor.progress, doc.progress) : doc.progress;
  const next = floor && floor.state === doc.state && floor.progress === progress ? floor : { state: doc.state, progress };
  return [progress === doc.progress ? doc : { ...doc, progress }, next];
}

type Link = "up" | "retrying" | "exhausted";

/**
 * Subscribe to `session_status/{id}` for the life of the page (PRD R4, D7). When the listener errors
 * (or the doc is missing) it resubscribes with backoff and, while it is down, polls
 * `["session-detail", id]`; after the last retry the poll continues and `fallback.exhausted` is set.
 * Mount with `key={id}` so each session starts from `loading`.
 */
export function useSessionStatus(id: string, quiet: RefObject<boolean>): StatusView {
  const client = useApiClient();
  const [view, setView] = useState<StatusView>({ phase: "loading" });
  const [link, setLink] = useState<Link>("up");
  // Highest server % seen in the current state (live and fallback share it): a late, lower doc cannot move the bar back.
  const [floor, setFloor] = useState<Floor | null>(null);
  const floorRef = useRef<Floor | null>(null); // same value for the listener callback, which cannot read state
  useEffect(() => {
    floorRef.current = floor;
  }, [floor]);

  useEffect(() => {
    let done = false;
    let generation = 0;
    let attempt = 0;
    let off: (() => void) | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    // Stale nudge: the listener alone never triggers the API's lazy stale check.
    let nudgeTimer: ReturnType<typeof setTimeout> | undefined;
    let lastNudgeAt = 0;
    let firstSeenAt = 0;
    const stopNudge = () => {
      clearTimeout(nudgeTimer);
      nudgeTimer = undefined;
      firstSeenAt = 0;
    };
    const armNudge = (doc: SessionStatusDoc, gen: number, afterMs: number) => {
      clearTimeout(nudgeTimer);
      const now = Date.now();
      firstSeenAt ||= now;
      const since = Date.parse(doc.stage_started_at ?? doc.updated_at);
      const dueAt = Math.max(
        (Number.isNaN(since) ? firstSeenAt : since) + afterMs,
        lastNudgeAt ? lastNudgeAt + STALE_NUDGE_EVERY_MS : 0,
      );
      nudgeTimer = setTimeout(() => {
        if (done || gen !== generation) return;
        lastNudgeAt = Date.now();
        // The listener shows the resulting `failed` by itself; the response and errors are ignored.
        void client
          .GET("/sessions/{id}", { params: { path: { id } } })
          .catch(() => undefined);
        armNudge(doc, gen, afterMs);
      }, Math.max(0, dueAt - now));
    };

    // Updates and errors that arrive while `quiet` (a DELETE in flight) are held, not lost: if the DELETE
    // fails, `quiet` clears and the latest one is replayed.
    let held: { gen: number; doc: SessionStatusDoc | null | "error" } | undefined;
    let heldTimer: ReturnType<typeof setInterval> | undefined;
    const hold = (gen: number, doc: SessionStatusDoc | null | "error") => {
      held = { gen, doc };
      heldTimer ??= setInterval(() => {
        if (done || quiet.current) return;
        clearInterval(heldTimer);
        heldTimer = undefined;
        const h = held;
        held = undefined;
        if (!h || h.gen !== generation) return;
        if (h.doc === "error" || h.doc === null) drop();
        else apply(h.doc, h.gen);
      }, QUIET_CHECK_MS);
    };

    const drop = () => {
      if (done || quiet.current) return;
      generation++;
      held = undefined;
      stopNudge();
      off?.();
      off = undefined;
      if (attempt < RESUBSCRIBE_DELAYS_MS.length) {
        setLink("retrying");
        retryTimer = setTimeout(connect, RESUBSCRIBE_DELAYS_MS[attempt++]);
      } else {
        setLink("exhausted");
      }
    };

    const apply = (incoming: SessionStatusDoc, gen: number) => {
      attempt = 0;
      setLink("up");
      const nudgeAfter = STALE_NUDGE_AFTER_BY_STATE[incoming.state];
      if (nudgeAfter !== undefined) armNudge(incoming, gen, nudgeAfter);
      else stopNudge();
      const [doc, nextFloor] = keepMax(floorRef.current, incoming);
      floorRef.current = nextFloor;
      setFloor(nextFloor);
      setView((prev) => ({
        phase: "live",
        doc,
        runStartedAt:
          doc.state !== "running"
            ? null
            : prev.phase === "live" && prev.doc.state === "running" && prev.runStartedAt !== null
              ? prev.runStartedAt
              : Date.parse(doc.started_at ?? "") || Date.parse(doc.updated_at) || Date.now(),
      }));
    };

    const connect = () => {
      const gen = ++generation;
      const unsubscribe = getStatusListener().subscribe(
        id,
        (doc) => {
          if (done || gen !== generation) return;
          if (quiet.current) return hold(gen, doc);
          if (doc === null) return drop();
          apply(doc, gen);
        },
        () => {
          if (gen !== generation) return;
          if (quiet.current) return hold(gen, "error");
          drop();
        },
      );
      off = unsubscribe;
      if (gen !== generation) {
        // dropped synchronously inside subscribe()
        unsubscribe();
        if (off === unsubscribe) off = undefined;
      }
    };

    connect();
    return () => {
      done = true;
      clearTimeout(retryTimer);
      clearInterval(heldTimer);
      stopNudge();
      off?.();
    };
  }, [id, client, quiet]);

  const poll = useQuery({
    queryKey: ["session-detail", id],
    enabled: link !== "up",
    refetchInterval: FALLBACK_POLL_MS,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}", { params: { path: { id } } })),
  });

  const [fallbackDoc, fallbackFloor] = useMemo(
    () => (poll.data ? keepMax(floor, detailToDoc(poll.data)) : [null, floor]),
    [poll.data, floor],
  );
  if (fallbackFloor !== floor) {
    // adjust state while rendering: the fallback doc raised the floor
    setFloor(fallbackFloor);
  }

  if (link === "up") return view;
  // 404 / 4xx (unknown or someone else's session) will not heal by polling.
  if (poll.isError && (!poll.data || (poll.error instanceof ApiError && poll.error.status < 500))) {
    return { phase: "error", error: describeLookupError(poll.error) };
  }
  if (fallbackDoc) return { phase: "fallback", doc: fallbackDoc, exhausted: link === "exhausted" };
  return view; // last live doc (or loading) until the first poll answers
}
