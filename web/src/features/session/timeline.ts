/**
 * Session timeline derived from `state` + flags. There is no per-gate
 * state: speaker and rating are flags, and `awaiting_input` is the one wait state.
 */
import { messageForCode } from "../../api/errors";
import { ratingEnabled } from "../../config";
import type { SessionStatusDoc } from "../../api/statusListener";

export type StepKey = "upload" | "transcribe" | "speaker" | "rating" | "run" | "report";
export type StepStatus = "done" | "current" | "pending" | "failed";

export interface TimelineStep {
  key: StepKey;
  label: string;
  status: StepStatus;
  subLabel?: string;
}

export interface Timeline {
  steps: TimelineStep[];
  /** One or more plain lines for the `aria-live` status text. */
  lines: string[];
  /** Show the run-progress block (elapsed time, bar) once the run has started. */
  showRunCopy: boolean;
  /** One-line leave/stay hint for the phase; null in terminal states. */
  hint: string | null;
  /** `awaiting_input` stopped by the daily cap: offer Start. */
  capReached: boolean;
}

export type TimelineInput = Pick<
  SessionStatusDoc,
  "state" | "step" | "error_code" | "transcript_ready" | "speaker_confirmed" | "rating_submitted"
>;

const LABELS: Record<StepKey, string> = {
  upload: "Upload",
  transcribe: "Transcribe",
  speaker: "Confirm speaker",
  rating: "Your rating",
  run: "Onolys scoring",
  report: "Report",
};
const ORDER = Object.keys(LABELS) as StepKey[];
export const STEP_LABELS = ORDER.map((k) => LABELS[k]);

const RUN_SUBLABELS: Record<string, string> = {
  code: "Coding the session",
  tips: "Writing tips",
  assemble: "Building the report",
};
const DEFAULT_SUBLABEL = RUN_SUBLABELS.code;

const TRANSCRIBE_CODES = new Set(["no_speech", "speakers_not_separated", "transcription_failed"]);

/** Which step a `failed` session stopped at, from the error code and what had finished. */
function failedAt(code: string | null, transcriptReady: boolean): StepKey {
  if (code && TRANSCRIBE_CODES.has(code)) return "transcribe";
  return transcriptReady ? "run" : "transcribe";
}

const HINT_UPLOAD = "Keep this tab open until upload finishes";
const HINT_BACKGROUND = "You can close this tab — we'll keep working";
const HINT_WAITING = "We'll wait here for your choice";

/** The one-line leave/stay hint per phase; null for terminal states. */
function hintFor(state: TimelineInput["state"]): string | null {
  switch (state) {
    case "created":
    case "uploading":
    case "upload_incomplete":
      return HINT_UPLOAD;
    case "validating":
    case "transcribing":
    case "running":
      return HINT_BACKGROUND;
    case "awaiting_input":
      return HINT_WAITING;
    default:
      return null;
  }
}

export interface TimelineOptions {
  /** Reset time for the cap message, already formatted for display. */
  resetsAt?: string;
  /** Show the "Your rating" step; off drops it. Defaults to the build flag. */
  ratingEnabled?: boolean;
}

export function deriveTimeline(doc: TimelineInput, opts: TimelineOptions = {}): Timeline {
  const rating = opts.ratingEnabled ?? ratingEnabled();
  const { state, transcript_ready: tr, speaker_confirmed: sp, rating_submitted: rt } = doc;
  const inputs = state === "awaiting_input";
  const afterTranscribe = inputs || state === "running" || state === "report_ready";
  const failedStep = state === "failed" ? failedAt(doc.error_code, tr) : null;
  const allPending = state === "deleting" || state === "cancelled" || state === "upload_failed";

  const status: Record<StepKey, StepStatus> = {
    upload: "pending",
    transcribe: "pending",
    speaker: "pending",
    rating: "pending",
    run: "pending",
    report: "pending",
  };

  if (!allPending) {
    // Upload / Transcribe (validating folds into it) follow the pipeline state.
    const uploadPhase = state === "created" || state === "uploading" || state === "upload_incomplete";
    status.upload = uploadPhase ? "current" : "done";
    status.transcribe =
      state === "transcribing" || state === "validating"
        ? "current"
        : uploadPhase
          ? "pending"
          : tr || afterTranscribe || state === "failed"
            ? "done"
            : "pending";
    if (state === "failed") {
      // Upload finished; Transcribe or Run failed; the rest stays pending.
      status.upload = "done";
      status.transcribe = failedStep === "transcribe" ? "failed" : "done";
      if (failedStep === "run") status.run = "failed";
    }

    // Gates come from the flags alone.
    status.speaker = sp || state === "report_ready" ? "done" : inputs ? "current" : "pending";
    status.rating = rt || state === "report_ready" ? "done" : inputs ? "current" : "pending";
    if (state === "running") status.run = "current";
    if (state === "report_ready") {
      status.run = "done";
      status.report = "done";
    }
  }

  const steps: TimelineStep[] = ORDER.filter((key) => key !== "rating" || rating).map((key) => ({
    key,
    label: LABELS[key],
    status: status[key],
  }));
  if (state === "validating") steps.find((s) => s.key === "transcribe")!.subLabel = "Checking audio";
  const runStep = steps.find((s) => s.key === "run")!;
  const runLabel = state === "running" ? (RUN_SUBLABELS[doc.step ?? ""] ?? DEFAULT_SUBLABEL) : undefined;
  if (runLabel) runStep.subLabel = runLabel;

  let capReached = false;
  let lines: string[];
  switch (state) {
    case "created":
      lines = ["Getting ready to upload your recording."];
      break;
    case "uploading":
      lines = ["Uploading your recording."];
      break;
    case "upload_incomplete":
      lines = ["Your upload didn't finish. Pick the file again to resume, or delete this session."];
      break;
    case "validating":
      lines = ["Checking your audio."];
      break;
    case "transcribing":
      lines = ["Transcribing the recording."];
      break;
    case "awaiting_input": {
      if (doc.error_code === "concurrent_runs") {
        // held by another running rating: Start is offered, and no reset time applies
        capReached = true;
        lines = [messageForCode(doc.error_code)];
        break;
      }
      if (doc.error_code === "daily_cap_reached") {
        capReached = true;
        lines = [messageForCode(doc.error_code, { resetsAt: opts.resetsAt })];
        break;
      }
      lines = [];
      if (!sp) lines.push("Confirm who the clinician is");
      if (!rt) lines.push(rating ? "Waiting for your rating" : "Waiting for your change goal");
      if (lines.length === 0) lines.push("Starting the rating.");
      break;
    }
    case "running":
      lines = [runLabel!];
      break;
    case "report_ready":
      lines = ["Your report is ready."];
      break;
    case "failed":
    case "upload_failed": // SessionPage shows its own view; this keeps the switch exhaustive
      lines = ["This session couldn't be completed."];
      break;
    case "cancelled": // SessionPage shows CancelledView before the timeline
      lines = ["This session was cancelled."];
      break;
    case "deleting":
      lines = ["Deleting this session."];
      break;
    default: {
      // A new SessionState must be handled above: this fails typecheck until it is.
      const unhandled: never = state;
      lines = [String(unhandled)];
    }
  }

  return { steps, lines, showRunCopy: state === "running", hint: hintFor(state), capReached };
}
