/**
 * Error codes (SP04 R9 `public-error-response`, plus the R4 table of the web
 * PRD) mapped to plain, fixed messages. Messages never include server text or
 * instance values (R8: no PHI in error messages).
 */
import type { components } from "./schema";

export const GENERIC_MESSAGE = "Something went wrong. Please try again.";

const MESSAGES = {
  transcript_invalid: "We couldn't read this transcript. Check its format and upload it again.",
  transcript_too_large: "This transcript is over 1 MB. Upload a smaller file.",
  empty_transcript: "The transcript needs at least 50 words. Upload a longer transcript.",
  session_too_long: "This session is too long to code. Use a narrower coded_span in the API.",
  invalid_coded_span: "The coded range is invalid. Check the range and try again.",
  unsupported_audio:
    "We can't use this file type. Upload an mp3, wav, m4a, webm or ogg recording.",
  audio_too_long: "This recording is longer than 20 minutes. Upload a shorter one.",
  audio_too_large:
    "This file is over 300 MB. Export it as m4a or mp3 and upload that instead.",
  audio_unreadable: "We couldn't read this audio file. Try exporting it again as m4a or mp3.",
  no_speech: "We couldn't hear enough speech in this recording",
  speakers_not_separated: "We couldn't tell the two speakers apart in this recording",
  transcription_failed: "Transcription didn't finish",
  rating_invalid: "Some of your rating needs a change. Check the highlighted fields.",
  upstream_unavailable: "A service we depend on is busy right now. Please try again in a minute.",
  daily_cap_reached: "You've reached today's limit.",
  interview_cap_reached: "You've reached your AI interview limit.",
  concurrent_runs: "You already have a rating running. Wait for it to finish.",
  email_unverified: "Verify your email address to continue. Open Verify email from the menu.",
  invalid_state: "That isn't possible at this stage of the session. Refresh and try again.",
  rate_limited: "You're going a little fast. Wait a moment and try again.",
  unauthenticated: "Your sign-in has expired. Please sign in again.",
  forbidden: "You don't have access to do that.",
  not_found: "We couldn't find that. It may have been deleted.",
  interview_too_long:
    "This interview recording is longer than allowed. Start a new practice interview.",
  rating_final: "Your rating is final. It can't be changed or run again.",
  conflict: "That request clashes with an earlier one. Refresh and try again.",
  internal_error: GENERIC_MESSAGE,
} as const satisfies Record<string, string>;

export type ErrorCode = keyof typeof MESSAGES;
export const ERROR_CODES = Object.keys(MESSAGES) as ErrorCode[];

function isKnown(code: string | undefined): code is ErrorCode {
  return code !== undefined && Object.hasOwn(MESSAGES, code);
}

export interface MessageContext {
  /** Reset time (a time of day) for the eval cap code, already formatted. */
  resetsAt?: string;
}

export function messageForCode(code: string | undefined, ctx: MessageContext = {}): string {
  if (!isKnown(code)) return GENERIC_MESSAGE;
  if (code === "daily_cap_reached" && ctx.resetsAt) {
    return `You've reached today's limit. You can start the rating after ${ctx.resetsAt}.`;
  }
  return MESSAGES[code];
}

/** Which recovery the error card offers (R4 Failure). */
export type FailureAction = "upload_new" | "try_again";

const UPLOAD_NEW = new Set<string>([
  "transcript_invalid",
  "transcript_too_large",
  "empty_transcript",
  "session_too_long",
  "unsupported_audio",
  "audio_too_long",
  "interview_too_long",
  "audio_too_large",
  "audio_unreadable",
  "no_speech",
  "speakers_not_separated",
  "transcription_failed",
]);

/**
 * FX45: a rating is final once submitted. A system failure offers "Try again" (re-runs the same
 * submission); a bad file, or no ready transcript (a retry is rejected with 409), needs a new upload.
 */
export function failureAction(code: string | undefined, transcriptReady: boolean): FailureAction {
  if (!transcriptReady) return "upload_new";
  return code !== undefined && UPLOAD_NEW.has(code) ? "upload_new" : "try_again";
}

type ErrorDetail = components["schemas"]["ErrorDetailModel"];

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];
  readonly requestId?: string;

  constructor(status: number, code: string, details: ErrorDetail[], requestId?: string) {
    super(`API error ${status} ${code}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  get userMessage(): string {
    return messageForCode(this.code);
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/** Turn a response body (expected: `public-error-response`) into an ApiError. */
export function parseErrorBody(status: number, body: unknown): ApiError {
  let details: ErrorDetail[] = [];
  let requestId: string | undefined;
  if (isRecord(body)) {
    if (Array.isArray(body.details)) {
      details = body.details.filter(
        (d): d is ErrorDetail =>
          isRecord(d) && typeof d.code === "string" && typeof d.message === "string",
      );
    }
    if (typeof body.request_id === "string") requestId = body.request_id;
  }
  let code: string | undefined = details[0]?.code;
  if (code === undefined) code = status === 429 ? "rate_limited" : "unknown";
  return new ApiError(status, code, details, requestId);
}

/**
 * An id in the URL that names nothing: 404, or 422 `invalid_parameters` (the API's answer for a
 * malformed, non-32-hex id). Pages with a session or report id show the same "not found" for both.
 */
export function isNotFoundError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || (err.status === 422 && err.code === "invalid_parameters"));
}

/** Like `describeError`, but a not-found-style error (see `isNotFoundError`) always reads as `not_found`. */
export function describeLookupError(err: unknown, ctx: MessageContext = {}): ErrorDescription {
  const d = describeError(err, ctx);
  return isNotFoundError(err) ? { ...d, code: "not_found", message: messageForCode("not_found") } : d;
}

export interface ErrorDescription {
  code: string;
  message: string;
  requestId?: string;
}

export function describeError(err: unknown, ctx: MessageContext = {}): ErrorDescription {
  if (err instanceof ApiError) {
    return {
      code: err.code,
      message: messageForCode(err.code, ctx),
      requestId: err.requestId,
    };
  }
  return { code: "unknown", message: GENERIC_MESSAGE, requestId: undefined };
}
