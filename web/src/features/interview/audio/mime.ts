/** Preferred recording containers: Chrome/Edge webm/opus, then bare webm, then Safari mp4. */
export const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"] as const;

/** First MediaRecorder-supported candidate, or "" (let the browser choose). */
export function pickMimeType(
  recorder: { isTypeSupported(type: string): boolean } | undefined = typeof MediaRecorder === "undefined"
    ? undefined
    : MediaRecorder,
): string {
  if (!recorder) return "";
  return MIME_CANDIDATES.find((m) => recorder.isTypeSupported(m)) ?? "";
}
