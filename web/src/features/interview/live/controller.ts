/**
 * Live interview controller (SP10 R8, R4): drives the relay socket and the audio engine, no UI.
 * Protocol: first message `{type:"auth", id_token}`; binary PCM16 16 kHz up; `ready`, binary PCM16 24 kHz,
 * `ai_speaking`, `interrupted`, `warn`, `time_up`, `error` down. A close that is not 1000 or 44xx is a dropped
 * connection: the same URL is retried for `reconnectWindowMs`; the recorder is paused meanwhile and resumed on
 * `ready{resumed:true}`, so the recording holds only connected time (matches the relay clock and the server limit).
 */
import type { AudioEngine } from "../audio/engine";
import { createRelaySocket } from "../relay/createRelaySocket";
import type { RelaySocket } from "../relay/fakeRelay";

export type Phase = "idle" | "connecting" | "live" | "reconnecting" | "ended" | "error";

export interface LiveState {
  phase: Phase;
  maxS: number;
  warnS: number;
  warned: boolean;
  timeUp: boolean;
  aiSpeaking: boolean;
  /** `connection_lost`, `signed_out`, `not_found`, `not_live`, `relay_error`, or null. */
  errorCode: string | null;
}

export interface ControllerOptions {
  url: string;
  getToken: () => Promise<string | null>;
  engine: Pick<AudioEngine, "playPcm24k" | "flush" | "pauseRecording" | "resumeRecording">;
  /** Defaults to `createRelaySocket` (the fake in mock builds). */
  createSocket?: (url: string) => RelaySocket;
  reconnectWindowMs?: number;
  retryDelayMs?: number;
  endWaitMs?: number;
  /** Fallbacks until the relay says `ready`. */
  limits?: { maxS: number; warnS: number };
}

export interface LiveController {
  getState(): LiveState;
  subscribe(fn: () => void): () => void;
  /** Seconds of interview time so far, ticking locally between relay messages. */
  elapsed(): number;
  start(): void;
  sendFrame(frame: ArrayBuffer): void;
  /** Ask the relay to end; resolves once the socket is closed (or at once when it is not connected). */
  requestEnd(): Promise<void>;
  dispose(): void;
}

const OPEN = 1;

export function createLiveController(opts: ControllerOptions): LiveController {
  const windowMs = opts.reconnectWindowMs ?? 60_000;
  const retryMs = opts.retryDelayMs ?? 1000;
  const endWaitMs = opts.endWaitMs ?? 3000;
  const makeSocket = opts.createSocket ?? ((u: string) => createRelaySocket(u));

  let state: LiveState = {
    phase: "idle",
    maxS: opts.limits?.maxS ?? 600,
    warnS: opts.limits?.warnS ?? 480,
    warned: false,
    timeUp: false,
    aiSpeaking: false,
    errorCode: null,
  };
  const listeners = new Set<() => void>();
  let socket: RelaySocket | undefined;
  let authed = false;
  let ending = false;
  let disposed = false;
  let firstDropAt: number | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let baseElapsed = 0;
  let baseAt = Date.now();
  const endWaiters: (() => void)[] = [];

  const set = (patch: Partial<LiveState>) => {
    state = { ...state, ...patch };
    listeners.forEach((l) => l());
  };
  const settleEnd = () => {
    endWaiters.splice(0).forEach((r) => r());
  };

  const terminal = (phase: "ended" | "error", errorCode: string | null = null) => {
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = undefined;
    set({ phase, errorCode, aiSpeaking: false });
    settleEnd();
  };

  const connect = () => {
    if (disposed) return;
    authed = false;
    const s = makeSocket(opts.url);
    socket = s;
    s.onopen = () => {
      void opts.getToken().then((token) => {
        if (socket !== s || disposed) return;
        if (!token) {
          s.close(1000);
          terminal("error", "signed_out");
          return;
        }
        s.send(JSON.stringify({ type: "auth", id_token: token }));
      });
    };
    s.onmessage = (ev) => {
      if (socket !== s) return;
      if (typeof ev.data !== "string") {
        opts.engine.playPcm24k(ev.data as ArrayBuffer);
        return;
      }
      let msg: { type?: string; resumed?: boolean; elapsed_s?: number; max_s?: number; warn_s?: number; code?: string };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      switch (msg.type) {
        case "ready":
          authed = true;
          firstDropAt = null;
          if (msg.resumed) opts.engine.resumeRecording();
          baseElapsed = msg.elapsed_s ?? 0;
          baseAt = Date.now();
          set({ phase: "live", maxS: msg.max_s ?? state.maxS, warnS: msg.warn_s ?? state.warnS, errorCode: null });
          break;
        case "ai_speaking":
          set({ aiSpeaking: Boolean((msg as { on?: boolean }).on) });
          break;
        case "interrupted":
          opts.engine.flush();
          break;
        case "warn":
          set({ warned: true });
          break;
        case "time_up":
          set({ timeUp: true });
          break;
        case "error":
          set({ errorCode: msg.code ?? "relay_error" });
          break;
      }
    };
    s.onclose = (ev) => {
      if (socket !== s || disposed) return;
      authed = false;
      const code = ev.code;
      if (code === 1000 || ending) return terminal("ended");
      if (code >= 4400 && code <= 4499) {
        const known: Record<number, string> = { 4401: "signed_out", 4404: "not_found", 4409: "not_live" };
        return terminal("error", known[code] ?? "relay_error");
      }
      // dropped: retry the same URL; the recorder pauses (connected time only)
      const now = Date.now();
      firstDropAt ??= now;
      if (now - firstDropAt >= windowMs) return terminal("error", "connection_lost");
      opts.engine.pauseRecording();
      set({ phase: "reconnecting" });
      retryTimer = setTimeout(connect, retryMs);
    };
  };

  return {
    getState: () => state,
    subscribe(fn) {
      listeners.add(fn);
      return () => void listeners.delete(fn);
    },
    elapsed() {
      return Math.min(state.maxS, baseElapsed + (Date.now() - baseAt) / 1000);
    },
    start() {
      if (state.phase !== "idle") return;
      set({ phase: "connecting" });
      connect();
    },
    sendFrame(frame) {
      if (authed && socket && socket.readyState === OPEN) socket.send(frame);
    },
    requestEnd() {
      if (ending && state.phase === "ended") return Promise.resolve();
      ending = true;
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = undefined;
      const s = socket;
      if (!s || !authed || s.readyState !== OPEN) {
        terminal("ended");
        return Promise.resolve();
      }
      return new Promise<void>((resolve) => {
        const t = setTimeout(() => terminal("ended"), endWaitMs);
        endWaiters.push(() => {
          clearTimeout(t);
          resolve();
        });
        s.send(JSON.stringify({ type: "end" }));
      });
    },
    dispose() {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      const s = socket;
      socket = undefined;
      try {
        s?.close(1000);
      } catch {
        /* already closed */
      }
      settleEnd();
    },
  };
}
