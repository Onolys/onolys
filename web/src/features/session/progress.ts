/**
 * Overall progress and Elapsed for the processing screen (05-processing-screen R3, D2-D4). Pure: the server owns
 * the base `progress` and `progress_next`; this only interpolates inside a stage.
 */
import type { SessionStatusDoc } from "../../api/statusListener";

export interface DerivedProgress {
  /** Integer 0-100; 100 only at `report_ready`, otherwise at most 99. */
  pct: number;
  /** Time since upload start, minus time waiting for the user. */
  elapsedMs: number;
  /** pct and Elapsed no longer move (waiting for the user, or done). */
  frozen: boolean;
  /** failed / cancelled / gone: show no bar, % or Elapsed. */
  hidden: boolean;
}

/** Expected seconds for a timed stage when the server sent no `stage_expected_s` (the server owns the formula, R6). */
export const DEFAULT_EXPECTED_S = 120;

/** States whose % moves with the clock (the page ticks once a second only while one is active). */
export function isTimedState(state: SessionStatusDoc["state"]): boolean {
  return state === "validating" || state === "transcribing" || state === "running";
}

const UPLOAD_STATES = new Set<SessionStatusDoc["state"]>(["created", "uploading", "upload_incomplete"]);

/** States before validation: the % follows upload bytes, but Elapsed still runs. */
export function isUploadState(state: SessionStatusDoc["state"]): boolean {
  return UPLOAD_STATES.has(state);
}
const HIDDEN_STATES = new Set<SessionStatusDoc["state"]>(["failed", "cancelled", "deleting", "upload_failed"]);

const ms = (iso: string | null | undefined): number | null => {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
};

function expectedSeconds(doc: SessionStatusDoc): number {
  if (doc.stage_expected_s != null && doc.stage_expected_s > 0) return doc.stage_expected_s;
  return DEFAULT_EXPECTED_S;
}

/** Highest value shown inside a stage: one below the next stage's base, never above 99. */
function stageCeiling(doc: SessionStatusDoc): number {
  const next = doc.progress_next ?? 99;
  return Math.min(99, Math.max(doc.progress, next - 1));
}

export function deriveProgress(doc: SessionStatusDoc, now: number, uploadFraction?: number | null): DerivedProgress {
  if (HIDDEN_STATES.has(doc.state)) return { pct: 0, elapsedMs: 0, frozen: true, hidden: true };

  const started = ms(doc.started_at);
  const waited = doc.waited_ms ?? 0;
  const elapsedAt = (at: number) => (started === null ? 0 : Math.max(0, at - started - waited));
  const stageStart = ms(doc.stage_started_at) ?? ms(doc.updated_at) ?? now;

  if (doc.state === "report_ready") {
    return { pct: 100, elapsedMs: elapsedAt(ms(doc.updated_at) ?? now), frozen: true, hidden: false };
  }
  if (doc.state === "awaiting_input") {
    // The current wait is not processing time: Elapsed stops at the moment the wait began.
    return { pct: Math.min(99, doc.progress), elapsedMs: elapsedAt(stageStart), frozen: true, hidden: false };
  }

  const base = doc.progress;
  let pct = base;
  if (UPLOAD_STATES.has(doc.state)) {
    if (uploadFraction != null && Number.isFinite(uploadFraction)) {
      const f = Math.min(1, Math.max(0, uploadFraction));
      const next = doc.progress_next ?? base;
      pct = Math.min(stageCeiling(doc), Math.floor(base + (next - base) * f));
    }
  } else if (isTimedState(doc.state)) {
    const t = Math.max(0, now - stageStart) / 1000;
    const x = 1 - Math.exp(-t / expectedSeconds(doc));
    pct = Math.floor(base + (stageCeiling(doc) - base) * x);
  }
  return { pct: Math.min(99, Math.max(base, pct)), elapsedMs: elapsedAt(now), frozen: false, hidden: false };
}
