/**
 * App-level uploader. One PUT of the whole object with XMLHttpRequest, sending exactly
 * the API's `required_headers`; auto-retry with a fresh URL up to 2 times, then the user retries
 * by hand. Jobs live in a module-level registry so they survive navigation to the session page.
 */
import { describeError, type ErrorDescription } from "../../api/errors";

export interface UploadTarget {
  upload_url: string;
  required_headers: Record<string, string>;
}

export type UploadPhase = "idle" | "uploading" | "completing" | "done" | "failed" | "cancelled";

export interface UploadState {
  phase: UploadPhase;
  loaded: number;
  total: number;
  /** 0 for the first PUT, 1 and 2 for the automatic retries. */
  attempt: number;
  /** Why the last `complete()` failed (the mapped API error), when it did. */
  error?: ErrorDescription;
}

export interface UploadJobOptions {
  file: Blob;
  /** The URL already issued by `POST …/audio`; later tries call `requestTarget`. */
  first?: UploadTarget;
  requestTarget: () => Promise<UploadTarget>;
  /** `POST …/audio/complete`. */
  complete: () => Promise<unknown>;
  createXhr?: () => XMLHttpRequest;
  /** Wait between automatic retries (injectable for tests). */
  delay?: (ms: number) => Promise<void>;
}

export const MAX_AUTO_RETRIES = 2;
/** Wait before automatic retry n (0-based): 1 s, 2 s. */
export const RETRY_BACKOFF_MS = 1000;
const MIN_TRANSFER_MS = 5 * 60_000;
const MIN_TRANSFER_BYTES_PER_S = 128 * 1024;

/** Deadline for one PUT: generous (assumes a slow 128 KiB/s link), never under 5 minutes. */
export function transferTimeoutMs(bytes: number): number {
  return Math.max(MIN_TRANSFER_MS, Math.ceil(bytes / MIN_TRANSFER_BYTES_PER_S) * 1000);
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export class UploadJob {
  private state: UploadState;
  private listeners = new Set<() => void>();
  private xhr: XMLHttpRequest | null = null;
  private run = 0;
  private uploaded = false;
  private first: UploadTarget | undefined;
  private file: Blob | null;
  private readonly opts: Omit<UploadJobOptions, "file">;
  /** Set by the registry: told when the state or the observers change. */
  onChange?: () => void;

  constructor(options: UploadJobOptions) {
    const { file, ...opts } = options;
    this.opts = opts;
    this.file = file;
    this.first = opts.first;
    this.state = { phase: "idle", loaded: 0, total: file.size, attempt: 0 };
  }

  /** False once the transfer finished: the File is released, only `complete()` can still be retried. */
  get holdsFile(): boolean {
    return this.file !== null;
  }

  /** Finished (or never to run again) and nobody is watching it. */
  get evictable(): boolean {
    return this.state.phase === "done" && this.listeners.size === 0;
  }

  getState = (): UploadState => this.state;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
      this.onChange?.();
    };
  };

  get active(): boolean {
    return this.state.phase === "uploading" || this.state.phase === "completing";
  }

  private set(patch: Partial<UploadState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l());
    this.onChange?.();
  }

  /** Start (or restart after failure/cancel) the upload. */
  start(): Promise<void> {
    if (this.active) return Promise.resolve();
    const id = ++this.run;
    if (this.uploaded) return this.finish(id);
    return this.upload(id);
  }

  retry(): Promise<void> {
    return this.start();
  }

  cancel(): void {
    if (!this.active) return;
    this.run++;
    this.set({ phase: "cancelled" });
    this.xhr?.abort();
    this.xhr = null;
  }

  private async upload(id: number): Promise<void> {
    this.set({ phase: "uploading", loaded: 0, attempt: 0, error: undefined });
    for (let attempt = 0; attempt <= MAX_AUTO_RETRIES; attempt++) {
      try {
        const target = this.first ?? (await this.opts.requestTarget());
        this.first = undefined;
        if (id !== this.run) return;
        this.set({ attempt, loaded: 0 });
        await this.put(target, id);
        this.uploaded = true;
        this.file = null; // the bytes are stored: release the File (a retry only calls complete())
        break;
      } catch {
        this.first = undefined; // a used or expired URL is never reused
        if (id !== this.run) return;
        if (attempt === MAX_AUTO_RETRIES) {
          this.set({ phase: "failed" });
          return;
        }
        await (this.opts.delay ?? sleep)(RETRY_BACKOFF_MS * 2 ** attempt);
        if (id !== this.run) return;
      }
    }
    if (id !== this.run) return;
    return this.finish(id);
  }

  private async finish(id: number): Promise<void> {
    this.set({ phase: "completing", loaded: this.state.total, error: undefined });
    try {
      await this.opts.complete();
      if (id === this.run) this.set({ phase: "done" });
    } catch (e) {
      if (id === this.run) this.set({ phase: "failed", error: describeError(e) });
    }
  }

  private put(target: UploadTarget, id: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = this.opts.createXhr ? this.opts.createXhr() : new XMLHttpRequest();
      this.xhr = xhr;
      const file = this.file;
      if (!file) return reject(new Error("file released"));
      xhr.open("PUT", target.upload_url);
      xhr.timeout = transferTimeoutMs(file.size); // a stall reaches ontimeout and the retry path
      for (const [k, v] of Object.entries(target.required_headers)) xhr.setRequestHeader(k, v);
      xhr.upload.onprogress = (e) => {
        if (id === this.run && e.lengthComputable) this.set({ loaded: e.loaded, total: e.total });
      };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`PUT ${xhr.status}`)));
      xhr.onerror = () => reject(new Error("network"));
      xhr.ontimeout = () => reject(new Error("timeout"));
      xhr.onabort = () => reject(new Error("aborted"));
      xhr.send(file);
    });
  }
}

// ---- registry + unload guard ------------------------------------------------

const jobs = new Map<string, UploadJob>();
const registryListeners = new Set<() => void>();

function evict(sessionId: string, job: UploadJob): void {
  if (jobs.get(sessionId) !== job) return;
  job.onChange = undefined;
  jobs.delete(sessionId);
  registryListeners.forEach((l) => l());
}

export function registerJob(sessionId: string, job: UploadJob): void {
  // Finished jobs nobody watches are dead weight (and may hold state): forget them first.
  jobs.forEach((j, id) => {
    if (id !== sessionId && j.evictable) evict(id, j);
  });
  jobs.get(sessionId)?.cancel();
  jobs.set(sessionId, job);
  // A finished job leaves the registry once its last observer is gone (a recheck, so a React
  // resubscribe in the same commit does not evict it).
  job.onChange = () => {
    if (job.evictable) setTimeout(() => job.evictable && evict(sessionId, job), 0);
  };
  registryListeners.forEach((l) => l());
}

/** Forget one session's job (session deleted, or no longer needed): cancels it if it still runs. */
export function dropJob(sessionId: string): void {
  const job = jobs.get(sessionId);
  if (!job) return;
  job.cancel();
  evict(sessionId, job);
}

/** Cancel every job and forget them (user changed: no File may outlive its owner). */
export function clearJobs(): void {
  jobs.forEach((j) => j.cancel());
  jobs.clear();
  registryListeners.forEach((l) => l());
}

export function getJob(sessionId: string): UploadJob | undefined {
  return jobs.get(sessionId);
}

export function subscribeRegistry(fn: () => void): () => void {
  registryListeners.add(fn);
  return () => void registryListeners.delete(fn);
}

export function activeUploadCount(): number {
  let n = 0;
  jobs.forEach((j) => {
    if (j.active) n++;
  });
  return n;
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", (e) => {
    if (activeUploadCount() > 0) {
      e.preventDefault();
      e.returnValue = ""; // legacy browsers need a value to show the prompt
    }
  });
}
