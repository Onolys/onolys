/**
 * In-page stand-in for the voice relay, for mock builds, PR previews and tests.
 * Plays the relay protocol over a WebSocket-shaped object: auth -> `ready`, 24 kHz PCM16 frames with
 * `ai_speaking`, `warn` at warn_s, `time_up` at max_s, `end`, and a simulated drop + reconnect (`resumed`).
 * Time is test-controllable: `autoTick: false` then `advance(seconds)`.
 */

export interface FakeRelayConfig {
  maxS: number;
  warnS: number;
  /** Run a real-time timer; false = only `advance()` moves the clock (tests). */
  autoTick: boolean;
  /** Audio frame period in ms of interview time (also the real timer period when autoTick). */
  frameMs: number;
  /** Frames the AI speaks / stays silent per cycle. */
  speakFrames: number;
  silentFrames: number;
}

const DEFAULTS: FakeRelayConfig = { maxS: 600, warnS: 480, autoTick: true, frameMs: 100, speakFrames: 20, silentFrames: 20 };
let config: FakeRelayConfig = { ...DEFAULTS };

interface Conv {
  elapsed: number;
  warned: boolean;
  timeUp: boolean;
  ended: boolean;
  frames: number;
}
const convs = new Map<string, Conv>();
const instances: FakeRelaySocket[] = [];

/** Override timing (call before connecting). */
export function configureFakeRelay(o: Partial<FakeRelayConfig>): void {
  config = { ...config, ...o };
}

/** Forget all conversations and live sockets; restore defaults (between tests). */
export function resetFakeRelay(): void {
  for (const s of instances.splice(0)) s.dispose();
  convs.clear();
  config = { ...DEFAULTS };
}

/** The most recently created fake socket (undefined if none). */
export function lastFakeRelay(): FakeRelaySocket | undefined {
  return instances[instances.length - 1];
}

const CONNECTING = 0;
const OPEN = 1;
const CLOSING = 2;
const CLOSED = 3;

type Handler = ((ev: Event) => void) | null;

/** The slice of `WebSocket` the interview feature uses; a real `WebSocket` satisfies it. */
export interface RelaySocket extends EventTarget {
  readonly readyState: number;
  binaryType: BinaryType;
  onopen: Handler;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: Handler;
  send(data: string | ArrayBuffer | Int16Array<ArrayBuffer>): void;
  close(code?: number, reason?: string): void;
}

export class FakeRelaySocket extends EventTarget implements RelaySocket {
  static readonly CONNECTING = CONNECTING;
  static readonly OPEN = OPEN;
  static readonly CLOSING = CLOSING;
  static readonly CLOSED = CLOSED;

  readyState = CONNECTING;
  binaryType: BinaryType = "arraybuffer";
  onopen: Handler = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: Handler = null;
  /** Binary frames the client sent (PCM16 16 kHz), for assertions. */
  readonly received: ArrayBuffer[] = [];

  private readonly id: string;
  private authed = false;
  private timer: ReturnType<typeof setInterval> | undefined;
  private speaking = false;
  private cycle = 0;
  private disposed = false;

  constructor(readonly url: string) {
    super();
    this.id = /\/v1\/voice\/([^/?#]+)/.exec(url)?.[1] ?? "";
    instances.push(this);
    queueMicrotask(() => {
      if (this.disposed || this.readyState !== CONNECTING) return;
      this.readyState = OPEN;
      this.fire("open", new Event("open"));
    });
  }

  send(data: string | ArrayBuffer | Int16Array<ArrayBuffer>): void {
    if (this.readyState !== OPEN) throw new DOMException("not open", "InvalidStateError");
    if (typeof data !== "string") {
      if (this.authed) this.received.push(data instanceof ArrayBuffer ? data : data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
      return;
    }
    let msg: { type?: string; id_token?: string };
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    if (!this.authed) {
      if (msg.type !== "auth" || !msg.id_token) return this.closeWith(4401);
      return this.accept();
    }
    if (msg.type === "end") {
      const c = convs.get(this.id);
      if (c) c.ended = true;
      this.closeWith(1000);
    }
  }

  close(code = 1000, reason = ""): void {
    this.closeWith(code, reason);
  }

  /** Test control: move interview time forward; emits audio, `warn`, `time_up` as thresholds pass. */
  advance(seconds: number): void {
    const c = convs.get(this.id);
    if (!c || !this.authed || this.readyState !== OPEN) return;
    const step = config.frameMs / 1000;
    let left = seconds;
    while (left > 1e-9 && this.readyState === OPEN) {
      const dt = Math.min(step, left);
      left -= dt;
      this.tick(c, dt);
    }
  }

  /** Test control: abrupt network drop (close 1006). The conversation survives; reconnect resumes it. */
  drop(): void {
    this.closeWith(1006);
  }

  dispose(): void {
    this.disposed = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    this.readyState = CLOSED;
  }

  private accept(): void {
    if (!this.id) return this.closeWith(4404);
    let c = convs.get(this.id);
    if (c?.ended || c?.timeUp) {
      this.sendJson({ type: "error", code: "not_live" });
      return this.closeWith(4409);
    }
    const resumed = c !== undefined;
    if (!c) convs.set(this.id, (c = { elapsed: 0, warned: false, timeUp: false, ended: false, frames: 0 }));
    this.authed = true;
    this.sendJson({ type: "ready", resumed, elapsed_s: round(c.elapsed), max_s: config.maxS, warn_s: config.warnS });
    if (config.autoTick) this.timer = setInterval(() => this.tick(c, config.frameMs / 1000), config.frameMs);
  }

  private tick(c: Conv, dt: number): void {
    c.elapsed = Math.min(c.elapsed + dt, config.maxS);
    const speak = this.cycle < config.speakFrames;
    this.cycle = (this.cycle + 1) % (config.speakFrames + config.silentFrames);
    if (speak !== this.speaking) {
      this.speaking = speak;
      this.sendJson({ type: "ai_speaking", on: speak });
    }
    if (speak) this.sendBinary(frame(c.frames++));
    if (!c.warned && c.elapsed >= config.warnS) {
      c.warned = true;
      this.sendJson({ type: "warn", at_s: config.warnS });
    }
    if (c.elapsed >= config.maxS && !c.timeUp) {
      c.timeUp = true;
      this.sendJson({ type: "time_up" });
      this.closeWith(1000);
    }
  }

  private closeWith(code: number, reason = ""): void {
    if (this.readyState === CLOSED) return;
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    this.readyState = CLOSED;
    queueMicrotask(() => {
      const ev = typeof CloseEvent === "function" ? new CloseEvent("close", { code, reason, wasClean: code !== 1006 }) : Object.assign(new Event("close"), { code, reason, wasClean: code !== 1006 });
      this.fire("close", ev);
    });
  }

  private sendJson(o: object): void {
    this.deliver(JSON.stringify(o));
  }

  private sendBinary(b: ArrayBuffer): void {
    this.deliver(b);
  }

  private deliver(data: string | ArrayBuffer): void {
    if (this.readyState !== OPEN) return;
    this.fire("message", new MessageEvent("message", { data }));
  }

  private fire(type: "open" | "message" | "close", ev: Event): void {
    this.dispatchEvent(ev);
    const h = (this as unknown as Record<string, ((e: Event) => void) | null>)["on" + type];
    h?.call(this, ev);
  }
}

const round = (n: number) => Math.round(n * 1000) / 1000;

/** 100 ms of a quiet 220 Hz tone: PCM16 mono at 24 kHz (frame `n` keeps the phase continuous). */
function frame(n: number): ArrayBuffer {
  const samples = 2400;
  const buf = new ArrayBuffer(samples * 2);
  const view = new DataView(buf);
  for (let i = 0; i < samples; i++) {
    const t = (n * samples + i) / 24000;
    view.setInt16(i * 2, Math.round(Math.sin(2 * Math.PI * 220 * t) * 3000), true);
  }
  return buf;
}
