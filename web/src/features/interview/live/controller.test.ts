/** Controller reconnect rules: recorder resume on any `ready`; the reconnect budget resets on content only. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createLiveController } from "./controller";
import type { RelaySocket } from "../relay/fakeRelay";

class Sock extends EventTarget implements RelaySocket {
  readyState = 0;
  binaryType: BinaryType = "arraybuffer";
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send() {}
  close() {}
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  say(obj: object) {
    this.onmessage?.({ data: JSON.stringify(obj) } as MessageEvent);
  }
  audio() {
    this.onmessage?.({ data: new ArrayBuffer(8) } as MessageEvent);
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code } as CloseEvent);
  }
}

function setup() {
  const socks: Sock[] = [];
  const engine = { playPcm24k: vi.fn(), flush: vi.fn(), pauseRecording: vi.fn(), resumeRecording: vi.fn() };
  const c = createLiveController({
    url: "ws://x",
    getToken: async () => "t",
    engine,
    createSocket: () => {
      const s = new Sock();
      socks.push(s);
      return s;
    },
    reconnectWindowMs: 5000,
    retryDelayMs: 1000,
  });
  c.start();
  return { c, socks, engine };
}

const ready = (resumed: boolean) => ({ type: "ready", resumed, elapsed_s: 0, max_s: 600, warn_s: 480 });

describe("live controller reconnect", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("resumes the recorder on a non-resumed ready after a first-connect drop", async () => {
    const { socks, engine } = setup();
    socks[0].drop();
    expect(engine.pauseRecording).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
    socks[1].open();
    await vi.advanceTimersByTimeAsync(0);
    socks[1].say(ready(false));
    expect(engine.resumeRecording).toHaveBeenCalled();
  });

  it("does not reset the reconnect budget on ready alone, only on content", async () => {
    const { c, socks } = setup();
    socks[0].drop();
    // upstream opens then fails right after ready, repeatedly: budget must run out
    for (let i = 1; i <= 8 && c.getState().phase !== "error"; i++) {
      await vi.advanceTimersByTimeAsync(1000);
      const s = socks[i];
      if (!s) break;
      s.open();
      await vi.advanceTimersByTimeAsync(0);
      s.say(ready(true));
      s.drop();
    }
    expect(c.getState().phase).toBe("error");
    expect(c.getState().errorCode).toBe("connection_lost");
  });

  it("resets the budget once content arrives after ready", async () => {
    const { c, socks } = setup();
    socks[0].drop();
    for (let i = 1; i <= 8; i++) {
      await vi.advanceTimersByTimeAsync(1000);
      const s = socks[i];
      s.open();
      await vi.advanceTimersByTimeAsync(0);
      s.say(ready(true));
      s.audio();
      s.drop();
    }
    expect(c.getState().phase).toBe("reconnecting");
  });
});

describe("live controller token failure", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const make = (getToken: () => Promise<string | null>) => {
    const socks: (Sock & { closed?: number })[] = [];
    const engine = { playPcm24k: vi.fn(), flush: vi.fn(), pauseRecording: vi.fn(), resumeRecording: vi.fn() };
    const c = createLiveController({
      url: "ws://x",
      getToken,
      engine,
      createSocket: () => {
        const s = new Sock() as Sock & { closed?: number };
        s.close = () => {
          s.closed = (s.closed ?? 0) + 1;
        };
        socks.push(s);
        return s;
      },
      reconnectWindowMs: 3000,
      retryDelayMs: 1000,
    });
    c.start();
    return { c, socks, engine };
  };

  it("a rejected getToken is handled: socket closed, reconnect policy applies, ends in an error", async () => {
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    const { c, socks } = make(() => Promise.reject(new Error("token")));
    socks[0].open();
    await vi.advanceTimersByTimeAsync(0);
    expect(socks[0].closed).toBe(1);
    expect(c.getState().phase).toBe("reconnecting");
    for (let i = 1; i < 6 && c.getState().phase === "reconnecting"; i++) {
      await vi.advanceTimersByTimeAsync(1000);
      socks[i]?.open();
      await vi.advanceTimersByTimeAsync(0);
    }
    expect(c.getState().phase).toBe("error");
    expect(c.getState().errorCode).toBe("connection_lost");
    await vi.advanceTimersByTimeAsync(0);
    process.off("unhandledRejection", unhandled);
    expect(unhandled).not.toHaveBeenCalled();
  });

  it("dispose wins over a late token rejection", async () => {
    let rej!: (e: Error) => void;
    const { c, socks } = make(() => new Promise<string | null>((_, r) => (rej = r)));
    socks[0].open();
    c.dispose();
    rej(new Error("late"));
    await vi.advanceTimersByTimeAsync(5000);
    expect(socks).toHaveLength(1);
    expect(c.getState().phase).toBe("connecting");
  });
});
