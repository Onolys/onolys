import { afterEach, describe, expect, it } from "vitest";
import { createRelaySocket } from "./createRelaySocket";
import { configureFakeRelay, FakeRelaySocket, lastFakeRelay, resetFakeRelay } from "./fakeRelay";

const URL_ = "wss://relay.mock.invalid/v1/voice/iv_1";

type Log = { json: Record<string, unknown>[]; bin: ArrayBuffer[]; close?: { code: number } };

function connect(url = URL_, auth = true) {
  const s = createRelaySocket(url, { fake: true }) as FakeRelaySocket;
  const log: Log = { json: [], bin: [] };
  s.onmessage = (e) => (typeof e.data === "string" ? log.json.push(JSON.parse(e.data)) : log.bin.push(e.data));
  s.onclose = (e) => (log.close = { code: e.code });
  const opened = new Promise<void>((r) => (s.onopen = () => r()));
  return { s, log, opened, auth: async () => { await opened; if (auth) s.send(JSON.stringify({ type: "auth", id_token: "t" })); } };
}
const flush = () => new Promise((r) => setTimeout(r, 0));
const types = (l: Log) => l.json.map((m) => m.type);

afterEach(() => resetFakeRelay());

describe("fake relay", () => {
  it("createRelaySocket returns the fake when asked, with arraybuffer binary type", () => {
    const s = createRelaySocket(URL_, { fake: true });
    expect(s).toBeInstanceOf(FakeRelaySocket);
    expect(s.binaryType).toBe("arraybuffer");
  });

  it("opens, then answers auth with ready (not resumed)", async () => {
    configureFakeRelay({ autoTick: false });
    const { s, log, auth } = connect();
    expect(s.readyState).toBe(0);
    await auth();
    expect(s.readyState).toBe(1);
    expect(log.json).toEqual([{ type: "ready", resumed: false, elapsed_s: 0, max_s: 600, warn_s: 480 }]);
  });

  it("closes 4401 when the first message is not a valid auth", async () => {
    const { s, log, opened } = connect();
    await opened;
    s.send(JSON.stringify({ type: "end" }));
    await flush();
    expect(log.close?.code).toBe(4401);
    expect(log.json).toEqual([]);
  });

  it("closes 4404 for a url with no interview id", async () => {
    const { log, auth } = connect("wss://relay.mock.invalid/v1/voice/");
    await auth();
    await flush();
    expect(log.close?.code).toBe(4404);
  });

  it("emits ai_speaking and 24 kHz PCM16 frames as time advances; ignores audio before auth", async () => {
    configureFakeRelay({ autoTick: false, speakFrames: 3, silentFrames: 2 });
    const { s, log, auth } = connect();
    await auth();
    s.advance(0.5); // 5 frames of 100 ms: speak on, 3 audio frames... then silence
    expect(types(log)).toEqual(["ready", "ai_speaking", "ai_speaking"]);
    expect(log.json[1]).toMatchObject({ on: true });
    expect(log.json[2]).toMatchObject({ on: false });
    expect(log.bin.length).toBe(3);
    expect(log.bin[0].byteLength).toBe(2400 * 2); // 100 ms at 24 kHz, 16-bit
    expect(new Int16Array(log.bin[0]).some((v) => v !== 0)).toBe(true);
  });

  it("records client audio only after auth", async () => {
    configureFakeRelay({ autoTick: false });
    const { s, auth } = connect();
    await auth();
    s.send(new Int16Array(160).buffer);
    expect(s.received).toHaveLength(1);
    expect(s.received[0].byteLength).toBe(320);
  });

  it("sends warn at warn_s once, then time_up at max_s and closes 1000", async () => {
    configureFakeRelay({ autoTick: false, maxS: 10, warnS: 6, frameMs: 500 });
    const { s, log, auth } = connect();
    await auth();
    s.advance(5.9);
    expect(types(log)).not.toContain("warn");
    s.advance(0.2);
    s.advance(1);
    expect(log.json.filter((m) => m.type === "warn")).toEqual([{ type: "warn", at_s: 6 }]);
    s.advance(100);
    expect(types(log).filter((t) => t === "time_up")).toHaveLength(1);
    await flush();
    expect(log.close?.code).toBe(1000);
    expect(types(log).at(-1)).toBe("time_up");
  });

  it("drop closes 1006; reconnect gets ready resumed:true with elapsed carried and no second warn", async () => {
    configureFakeRelay({ autoTick: false, maxS: 20, warnS: 5, frameMs: 500 });
    const a = connect();
    await a.auth();
    a.s.advance(7);
    a.s.drop();
    await flush();
    expect(a.log.close?.code).toBe(1006);
    expect(a.log.json.filter((m) => m.type === "warn")).toHaveLength(1);

    const b = connect();
    await b.auth();
    expect(b.log.json[0]).toEqual({ type: "ready", resumed: true, elapsed_s: 7, max_s: 20, warn_s: 5 });
    expect(lastFakeRelay()).toBe(b.s);
    b.s.advance(20);
    expect(types(b.log)).not.toContain("warn");
    expect(types(b.log)).toContain("time_up");
  });

  it("end closes 1000, and reconnecting an ended interview gets error + 4409", async () => {
    configureFakeRelay({ autoTick: false });
    const a = connect();
    await a.auth();
    a.s.send(JSON.stringify({ type: "end" }));
    await flush();
    expect(a.log.close?.code).toBe(1000);
    const b = connect();
    await b.auth();
    await flush();
    expect(b.log.json).toEqual([{ type: "error", code: "not_live" }]);
    expect(b.log.close?.code).toBe(4409);
  });

  it("auto-ticks in real time when enabled", async () => {
    configureFakeRelay({ autoTick: true, frameMs: 5, speakFrames: 100, silentFrames: 0 });
    const { log, auth } = connect();
    await auth();
    await new Promise((r) => setTimeout(r, 60));
    expect(log.bin.length).toBeGreaterThan(2);
  });
});
