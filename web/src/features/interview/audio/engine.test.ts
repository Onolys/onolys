import { afterEach, describe, expect, it, vi } from "vitest";
import { pickMimeType } from "./mime";

vi.mock("./workletUrls", () => ({ captureUrl: "/capture.js", playbackUrl: "/playback.js" }));

const recorderSupporting = (...ok: string[]) => ({ isTypeSupported: (t: string) => ok.includes(t) });

describe("pickMimeType", () => {
  it("prefers webm/opus", () => {
    expect(pickMimeType(recorderSupporting("audio/webm;codecs=opus", "audio/webm", "audio/mp4"))).toBe("audio/webm;codecs=opus");
  });
  it("falls back to webm, then mp4 (Safari)", () => {
    expect(pickMimeType(recorderSupporting("audio/webm", "audio/mp4"))).toBe("audio/webm");
    expect(pickMimeType(recorderSupporting("audio/mp4"))).toBe("audio/mp4");
  });
  it("returns empty when none or no MediaRecorder", () => {
    expect(pickMimeType(recorderSupporting())).toBe("");
    expect(pickMimeType(undefined)).toBe("");
  });
});

describe("createAudioEngine (mocked browser)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("wires mic+AI into one recorder, forwards frames, flushes, stops with a Blob", async () => {
    const node = () => ({ connect: vi.fn((n) => n), port: { postMessage: vi.fn(), onmessage: null as unknown } });
    const nodes: ReturnType<typeof node>[] = [];
    const dest = { stream: { id: "dest" } };
    class FakeCtx {
      destination = {};
      audioWorklet = { addModule: vi.fn(async () => {}) };
      resume = vi.fn(async () => {});
      close = vi.fn(async () => {});
      createMediaStreamDestination = () => dest;
      createMediaStreamSource = () => node();
      createGain = () => ({ ...node(), gain: { value: 1 } });
    }
    class FakeNode {
      constructor() {
        const n = node();
        nodes.push(n);
        return n;
      }
    }
    const recorders: FakeRecorder[] = [];
    class FakeRecorder {
      static isTypeSupported = (t: string) => t === "audio/mp4";
      mimeType: string;
      state = "recording";
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start = vi.fn();
      constructor(public s: unknown, o?: { mimeType: string }) {
        this.mimeType = o?.mimeType ?? "";
        recorders.push(this);
      }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["abc"]) });
        this.onstop?.();
      }
    }
    const track = { stop: vi.fn() };
    const gum = vi.fn(async () => ({ getTracks: () => [track] }));
    vi.stubGlobal("AudioContext", FakeCtx);
    window.AudioContext = FakeCtx as never;
    vi.stubGlobal("AudioWorkletNode", FakeNode);
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: gum }, configurable: true });

    const { createAudioEngine } = await import("./engine");
    const frames: ArrayBuffer[] = [];
    const e = createAudioEngine({ onCaptureFrame: (f) => frames.push(f) });
    await e.start();

    expect(gum).toHaveBeenCalledWith({ audio: expect.objectContaining({ echoCancellation: true, noiseSuppression: true }) });
    expect(e.mimeType).toBe("audio/mp4");
    const recorder = recorders[0];
    expect(recorder.s).toBe(dest.stream);
    expect(recorder.start).toHaveBeenCalled();

    const [cap, play] = nodes;
    (cap.port.onmessage as (m: unknown) => void)({ data: new ArrayBuffer(640) });
    expect(frames).toHaveLength(1);

    e.playPcm24k(new Int16Array([1, 2, 3]));
    expect(play.port.postMessage).toHaveBeenCalledWith(expect.any(ArrayBuffer), [expect.any(ArrayBuffer)]);
    e.flush();
    expect(play.port.postMessage).toHaveBeenLastCalledWith("flush");

    const blob = await e.stopRecording();
    expect(blob.size).toBe(3);
    expect(blob.type).toBe("audio/mp4");
    e.close();
    expect(track.stop).toHaveBeenCalled();
  });
});
