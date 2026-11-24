/** Advisory client pre-checks (PRD R3 step 2). The server stays authoritative. */
/** Limits served by `GET /v1/upload-limits`; the only source of numbers and accepted types here. */
export interface UploadLimits {
  max_bytes: number;
  max_duration_s: number;
  interview_max_duration_s: number;
  short_warning_s: number;
  extensions: string[];
  mime_types: string[];
}

const BYTES_PER_MB = 1024 * 1024;
const SECONDS_PER_MINUTE = 60;
const minutes = (s: number) => Math.round((s / SECONDS_PER_MINUTE) * 10) / 10;

function listOf(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
}

const sizeMessage = (l: UploadLimits) =>
  `This file is over ${Math.round(l.max_bytes / BYTES_PER_MB)} MB. Export it as m4a or mp3 and upload that instead.`;
const typeMessage = (l: UploadLimits) => `We can't use this file type. Upload an ${listOf(l.extensions)} recording.`;
const longMessage = (l: UploadLimits) =>
  `This recording is longer than ${minutes(l.max_duration_s)} minutes. Upload a shorter one.`;
const shortWarning = (l: UploadLimits) =>
  `This recording is under ${minutes(l.short_warning_s)} minutes. Global scores can be unreliable on short sessions.`;

export interface PrecheckResult {
  blocked: string | null;
  warning: string | null;
}

export interface FileInfo {
  name: string;
  size: number;
  type: string;
}

export function fileExtension(name: string): string {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

/** Blocks/warns per the served limits. No limits (not loaded, request failed) = skip: the server decides. */
export function checkFile(
  file: FileInfo,
  durationSeconds?: number | null,
  limits?: UploadLimits | null,
): PrecheckResult {
  if (!limits) return { blocked: null, warning: null };
  if (file.size > limits.max_bytes) return { blocked: sizeMessage(limits), warning: null };
  // By extension or by MIME: browsers report webm audio inconsistently (webm often arrives as video), so a
  // served extension alone is enough.
  const typeOk =
    limits.extensions.includes(fileExtension(file.name)) || limits.mime_types.includes(file.type.toLowerCase());
  if (!typeOk) return { blocked: typeMessage(limits), warning: null };
  if (typeof durationSeconds === "number" && Number.isFinite(durationSeconds)) {
    if (durationSeconds > limits.max_duration_s) return { blocked: longMessage(limits), warning: null };
    if (durationSeconds < limits.short_warning_s) return { blocked: null, warning: shortWarning(limits) };
  }
  return { blocked: null, warning: null };
}

/** Duration from audio metadata; `null` when the browser cannot read it (checks then stay silent). */
export function readDuration(file: Blob, timeoutMs = 5000): Promise<number | null> {
  return new Promise((resolve) => {
    if (typeof URL.createObjectURL !== "function") return resolve(null);
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    let done = false;
    const finish = (v: number | null) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      audio.removeAttribute("src");
      URL.revokeObjectURL(url);
      resolve(v);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    audio.preload = "metadata";
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) ? audio.duration : null);
    audio.onerror = () => finish(null);
    audio.src = url;
  });
}

export const MAX_TRANSCRIPT_BYTES = 1024 * 1024;

export function checkTranscript(file: FileInfo): PrecheckResult {
  if (file.size > MAX_TRANSCRIPT_BYTES) return { blocked: "This transcript is over 1 MB. Upload a smaller file.", warning: null };
  if (!["json", "txt"].includes(fileExtension(file.name))) return { blocked: "Upload a json or txt transcript file.", warning: null };
  return { blocked: null, warning: null };
}
