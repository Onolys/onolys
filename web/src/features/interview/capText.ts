import { formatBlockingReset, type Blocking } from "../usage/usage";

/** The message under a disabled "Start AI Interview": the daily cap is spent and when it resets. */
export function interviewCapText(b: Blocking): string {
  const reset = formatBlockingReset(b);
  const tail = reset ? ` It resets at ${reset}.` : "";
  return `You've reached today's AI interview limit.${tail}`;
}

/** `m:ss`. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Recorder output -> an upload-ready File (codec parameters stripped from the type). */
export function recordingFile(blob: Blob): File {
  const type = (blob.type || "audio/webm").split(";")[0]!.trim().toLowerCase();
  const ext = type === "audio/mp4" ? "m4a" : type === "audio/ogg" ? "ogg" : "webm";
  return new File([blob], `interview.${ext}`, { type });
}
