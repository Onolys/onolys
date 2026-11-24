/**
 * Status-subscription seam (PRD R4/R7, D7). The session page subscribes to a
 * PHI-free `session_status/{id}` doc. Live mode backs this with Firestore
 * `onSnapshot` (a later task); mock mode uses the in-memory emitter below,
 * driven by the MSW state machine.
 */
import type { FailureKind } from "./errors";
import type { SessionState } from "./types";

export interface SessionStatusDoc {
  uid: string;
  /** `upload_failed` is a status-doc-only state (a bad upload leaves no session), so it is not in the OpenAPI enum. */
  state: SessionState | "upload_failed";
  step: string | null;
  progress: number;
  error_code: string | null;
  /** The status doc is a Firestore document, not an OpenAPI schema. Absent on docs written before 03-failure-policy. */
  error_kind?: FailureKind | null;
  retries_left?: number | null;
  counted?: boolean | null;
  latest_report_version: number | null;
  updated_at: string;
  /** Progress fields (05-processing-screen R2): PHI-free numbers and ISO timestamps, absent on older docs. */
  /** First entry to `uploading` (a re-run: its start); null before. */
  started_at?: string | null;
  /** When the current state was entered. */
  stage_started_at?: string | null;
  /** Total ms spent in `awaiting_input`. */
  waited_ms?: number;
  /** Recording duration in seconds, set once validated. */
  audio_s?: number | null;
  /** Base % of the next stage (99 on the last stage); null when there is none. */
  progress_next?: number | null;
  /** Typical seconds the current stage takes; null when untimed. */
  stage_expected_s?: number | null;
  transcript_ready: boolean;
  speaker_confirmed: boolean;
  rating_submitted: boolean;
  has_rating: boolean;
}

export type Unsubscribe = () => void;

export interface StatusListener {
  /**
   * `onStatus(null)` = the doc does not exist (deleted). `onError` = listener
   * failure or permission-denied; the caller polls `GET /sessions/{id}` and resubscribes with backoff.
   */
  subscribe(
    sessionId: string,
    onStatus: (doc: SessionStatusDoc | null) => void,
    onError: (err: Error) => void,
  ): Unsubscribe;
}

export interface MemoryStatusEmitter extends StatusListener {
  emit(sessionId: string, doc: SessionStatusDoc): void;
  emitError(sessionId: string, err: Error): void;
  remove(sessionId: string): void;
  clear(): void;
}

interface Sub {
  onStatus: (doc: SessionStatusDoc | null) => void;
  onError: (err: Error) => void;
}

export function createMemoryStatusEmitter(opts: { reportMissing?: boolean } = {}): MemoryStatusEmitter {
  const docs = new Map<string, SessionStatusDoc>();
  const subs = new Map<string, Set<Sub>>();

  const forEach = (sid: string, fn: (s: Sub) => void) => {
    for (const s of [...(subs.get(sid) ?? [])]) fn(s);
  };

  return {
    subscribe(sessionId, onStatus, onError) {
      const sub: Sub = { onStatus, onError };
      let set = subs.get(sessionId);
      if (!set) subs.set(sessionId, (set = new Set()));
      set.add(sub);
      const current = docs.get(sessionId);
      if (current) onStatus({ ...current });
      // Like Firestore's onSnapshot, a missing doc reports `null` (the page then asks the API, which answers 404).
      else if (opts.reportMissing) onStatus(null);
      return () => {
        subs.get(sessionId)?.delete(sub);
      };
    },
    emit(sessionId, doc) {
      docs.set(sessionId, { ...doc });
      forEach(sessionId, (s) => s.onStatus({ ...doc }));
    },
    emitError(sessionId, err) {
      forEach(sessionId, (s) => s.onError(err));
    },
    remove(sessionId) {
      docs.delete(sessionId);
      forEach(sessionId, (s) => s.onStatus(null));
    },
    clear() {
      docs.clear();
      subs.clear();
    },
  };
}

let active: StatusListener | null = null;

export function setStatusListener(listener: StatusListener | null): void {
  active = listener;
}

export function getStatusListener(): StatusListener {
  if (!active) throw new Error("No status listener registered (set one at app start).");
  return active;
}
