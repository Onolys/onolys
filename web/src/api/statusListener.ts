/**
 * Status-subscription seam. The session page subscribes to a
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
  /** The status doc is a Firestore document, not an OpenAPI schema. Absent on docs written before failure kinds were recorded. */
  error_kind?: FailureKind | null;
  retries_left?: number | null;
  counted?: boolean | null;
  latest_report_version: number | null;
  updated_at: string;
  /** Progress fields: PHI-free numbers and ISO timestamps, absent on older docs. */
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

const isoOrNull = (v: unknown): string | null => {
  if (typeof v === "string") return v;
  if (v && typeof (v as { toDate?: unknown }).toDate === "function") return (v as { toDate(): Date }).toDate().toISOString();
  return null;
};
const numOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/**
 * The one place a raw status doc (Firestore data with Timestamps, or the REST detail reshaped to the same keys)
 * becomes a `SessionStatusDoc`. Both the live listener and the REST fallback go through it so they cannot drift:
 * add a field to `SessionStatusDoc` here and both paths carry it.
 */
export function normalizeStatusDoc(d: Record<string, unknown>): SessionStatusDoc {
  return {
    uid: String(d.uid ?? ""),
    state: d.state as SessionStatusDoc["state"],
    step: typeof d.step === "string" ? d.step : null,
    progress: Number(d.progress ?? 0),
    error_code: typeof d.error_code === "string" ? d.error_code : null,
    error_kind: typeof d.error_kind === "string" ? (d.error_kind as FailureKind) : null,
    retries_left: numOrNull(d.retries_left),
    counted: typeof d.counted === "boolean" ? d.counted : null,
    latest_report_version: numOrNull(d.latest_report_version),
    updated_at: isoOrNull(d.updated_at) ?? new Date(0).toISOString(),
    started_at: isoOrNull(d.started_at),
    stage_started_at: isoOrNull(d.stage_started_at),
    waited_ms: numOrNull(d.waited_ms) ?? 0,
    audio_s: numOrNull(d.audio_s),
    progress_next: numOrNull(d.progress_next),
    stage_expected_s: numOrNull(d.stage_expected_s),
    transcript_ready: d.transcript_ready === true,
    speaker_confirmed: d.speaker_confirmed === true,
    rating_submitted: d.rating_submitted === true,
    has_rating: d.has_rating === true,
  };
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
