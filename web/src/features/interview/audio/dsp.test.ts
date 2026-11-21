import { describe, expect, it } from "vitest";
import { CAPTURE_FRAME_SAMPLES, CaptureFramer, floatToPcm16, PlaybackRing } from "./dsp";

describe("floatToPcm16", () => {
  it("scales and clamps", () => {
    expect(floatToPcm16(0)).toBe(0);
    expect(floatToPcm16(1)).toBe(32767);
    expect(floatToPcm16(-1)).toBe(-32768);
    expect(floatToPcm16(5)).toBe(32767);
    expect(floatToPcm16(-5)).toBe(-32768);
  });
});

describe("CaptureFramer", () => {
  it("48k -> 16k: 3:1 averaging, 320-sample frames", () => {
    const frames: Int16Array[] = [];
    const f = new CaptureFramer(48000, (fr) => frames.push(fr));
    f.push(new Float32Array(960).fill(0.5)); // 20 ms @ 48k
    expect(frames).toHaveLength(1);
    expect(frames[0]).toHaveLength(CAPTURE_FRAME_SAMPLES);
    expect(frames[0][0]).toBe(floatToPcm16(0.5));
    expect(frames[0][319]).toBe(floatToPcm16(0.5));
  });
  it("buffers across small blocks (128 samples) and emits no partial frames", () => {
    const frames: Int16Array[] = [];
    const f = new CaptureFramer(48000, (fr) => frames.push(fr));
    for (let i = 0; i < 7; i++) f.push(new Float32Array(128)); // 896 < 960
    expect(frames).toHaveLength(0);
    f.push(new Float32Array(128)); // 1024 >= 960
    expect(frames).toHaveLength(1);
  });
  it("44.1k fractional ratio yields ~16000 samples per second", () => {
    let n = 0;
    const f = new CaptureFramer(44100, (fr) => (n += fr.length));
    for (let i = 0; i < 44100 / 128; i++) f.push(new Float32Array(128));
    expect(n).toBeGreaterThanOrEqual(15680);
    expect(n).toBeLessThanOrEqual(16000);
  });
  it("16k passthrough keeps samples", () => {
    const frames: Int16Array[] = [];
    const f = new CaptureFramer(16000, (fr) => frames.push(fr));
    const ramp = Float32Array.from({ length: 320 }, (_, i) => i / 320);
    f.push(ramp);
    expect(frames[0][100]).toBe(floatToPcm16(100 / 320));
  });
});

describe("PlaybackRing", () => {
  it("24k -> 48k doubles length with linear interpolation (pitch preserved)", () => {
    const r = new PlaybackRing(48000);
    r.write(Float32Array.from([0, 1, 0, 1, 0, 1, 0, 1]));
    const out = new Float32Array(8);
    expect(r.read(out)).toBe(8);
    expect(Array.from(out)).toEqual([0, 0.5, 1, 0.5, 0, 0.5, 1, 0.5]);
  });
  it("24k -> 24k is identity", () => {
    const r = new PlaybackRing(24000);
    r.write(Float32Array.from([0.1, 0.2, 0.3, 0.4]));
    const out = new Float32Array(3);
    r.read(out);
    expect(out[0]).toBeCloseTo(0.1);
    expect(out[2]).toBeCloseTo(0.3);
  });
  it("underrun outputs silence and counts once", () => {
    const r = new PlaybackRing(24000);
    r.write(Float32Array.from([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]));
    const out = new Float32Array(8);
    expect(r.read(out)).toBe(8); // playing
    expect(r.read(out)).toBeLessThan(8);
    expect(out[7]).toBe(0);
    expect(r.underruns).toBe(1);
    r.read(out);
    expect(r.underruns).toBe(1);
  });
  it("flush drops queued audio", () => {
    const r = new PlaybackRing(24000);
    r.write(new Float32Array(1000).fill(1));
    r.flush();
    expect(r.buffered).toBe(0);
    const out = new Float32Array(4).fill(9);
    expect(r.read(out)).toBe(0);
    expect(Array.from(out)).toEqual([0, 0, 0, 0]);
  });
  it("overflow drops oldest audio", () => {
    const r = new PlaybackRing(24000, 4);
    r.write(Float32Array.from([1, 2, 3]));
    r.write(Float32Array.from([4, 5]));
    expect(r.buffered).toBe(4);
    const out = new Float32Array(1);
    r.read(out);
    expect(out[0]).toBe(2);
  });
  it("converts PCM16 input", () => {
    const r = new PlaybackRing(24000);
    r.writePcm16(Int16Array.from([-32768, 0, 16384]));
    const out = new Float32Array(2);
    r.read(out);
    expect(out[0]).toBe(-1);
    expect(out[1]).toBe(0);
  });
});
