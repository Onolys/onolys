/** Debounced, serialised draft saver. Framework-free so it is easy to test. */
export type SaveStatus = "idle" | "saving" | "saved" | "error" | "invalid";

export interface AutosaverOptions {
  /** Performs one draft PUT. Throws on failure. `keepalive` is true when flushing on page hide. */
  save: (keepalive: boolean) => Promise<void>;
  onStatus: (s: SaveStatus) => void;
  delayMs?: number;
  retryMs?: number;
  /** Failures that retrying cannot fix (e.g. 422 over the limit): stop, wait for the next change. */
  isPermanent?: (err: unknown) => boolean;
}

export interface Autosaver {
  change(): void;
  flush(opts?: { keepalive?: boolean }): Promise<void>;
  cancel(): void;
  dispose(): void;
}

export function createAutosaver(opts: AutosaverOptions): Autosaver {
  const { save, onStatus, delayMs = 2000, retryMs = 5000, isPermanent = () => false } = opts;
  let dirty = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let chain: Promise<void> = Promise.resolve();
  let disposed = false;
  let closing = false;

  const clear = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
  };
  const arm = (ms: number) => {
    clear();
    timer = setTimeout(() => void flush(), ms);
  };

  async function run(keepalive: boolean) {
    if (!dirty || disposed) return;
    dirty = false;
    onStatus("saving");
    try {
      await save(keepalive);
      if (!disposed) onStatus(dirty ? "saving" : "saved");
    } catch (err) {
      if (disposed) return;
      if (isPermanent(err)) {
        onStatus("invalid");
        return;
      }
      dirty = true;
      onStatus("error");
      if (!closing) arm(retryMs);
    }
  }

  function flush(o: { keepalive?: boolean } = {}) {
    clear();
    chain = chain.then(() => run(o.keepalive === true));
    return chain;
  }

  return {
    change() {
      if (closing) return;
      dirty = true;
      arm(delayMs);
    },
    flush,
    cancel() {
      clear(); // timer only: edits stay dirty so a later flush/blur/retry still saves them
    },
    dispose() {
      // Stop new edits/timers now, but let flushes already queued (unmount flush) run before gating run().
      closing = true;
      clear();
      chain = chain.then(() => {
        disposed = true;
      });
    },
  };
}
