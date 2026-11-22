import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type RefObject } from "react";
import { ApiError, describeLookupError, type ErrorDescription } from "../../api/errors";
import { unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { getStatusListener, type SessionStatusDoc } from "../../api/statusListener";
import { useApiClient } from "../../auth/useApiClient";

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

function detailToDoc(d: Detail): SessionStatusDoc {
  return {
    uid: "",
    state: d.status,
    step: d.step ?? null,
    progress: d.progress,
    error_code: d.error?.code ?? null,
    latest_report_version: d.latest_report_version ?? null,
    updated_at: new Date().toISOString(),
    ...d.flags,
  };
}

/** A session stuck in `transcribing` this long gets a `GET /sessions/{id}`, which makes the API settle it. */
export const STALE_NUDGE_AFTER_MS = 6 * 60_000;
/** While it stays `transcribing`, nudge at most this often. */
export const STALE_NUDGE_EVERY_MS = 60_000;

/** Resubscribe delays after a listener drop (D7); when they run out the page shows "Live updates stopped". */
export const RESUBSCRIBE_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000];
/** While the listener is down, poll the session detail this often. */
export const FALLBACK_POLL_MS = 5_000;

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
    const armNudge = (doc: SessionStatusDoc, gen: number) => {
      clearTimeout(nudgeTimer);
      const now = Date.now();
      firstSeenAt ||= now;
      const since = Date.parse(doc.updated_at);
      const dueAt = Math.max(
        (Number.isNaN(since) ? firstSeenAt : since) + STALE_NUDGE_AFTER_MS,
        lastNudgeAt ? lastNudgeAt + STALE_NUDGE_EVERY_MS : 0,
      );
      nudgeTimer = setTimeout(() => {
        if (done || gen !== generation) return;
        lastNudgeAt = Date.now();
        // The listener shows the resulting `failed` by itself; the response and errors are ignored.
        void client
          .GET("/sessions/{id}", { params: { path: { id } } })
          .catch(() => undefined);
        armNudge(doc, gen);
      }, Math.max(0, dueAt - now));
    };

    const drop = () => {
      if (done || quiet.current) return;
      generation++;
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

    const connect = () => {
      const gen = ++generation;
      const unsubscribe = getStatusListener().subscribe(
        id,
        (doc) => {
          if (done || gen !== generation || quiet.current) return;
          if (doc === null) return drop();
          attempt = 0;
          setLink("up");
          if (doc.state === "transcribing") armNudge(doc, gen);
          else stopNudge();
          setView((prev) => ({
            phase: "live",
            doc,
            runStartedAt:
              doc.state !== "running"
                ? null
                : prev.phase === "live" && prev.doc.state === "running" && prev.runStartedAt !== null
                  ? prev.runStartedAt
                  : Date.parse(doc.updated_at) || Date.now(),
          }));
        },
        () => {
          if (gen === generation) drop();
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

  const fallbackDoc = useMemo(() => (poll.data ? detailToDoc(poll.data) : null), [poll.data]);

  if (link === "up") return view;
  // 404 / 4xx (unknown or someone else's session) will not heal by polling.
  if (poll.isError && (!poll.data || (poll.error instanceof ApiError && poll.error.status < 500))) {
    return { phase: "error", error: describeLookupError(poll.error) };
  }
  if (fallbackDoc) return { phase: "fallback", doc: fallbackDoc, exhausted: link === "exhausted" };
  return view; // last live doc (or loading) until the first poll answers
}
