import { describe, expect, it } from "vitest";
import type { SessionStatusDoc } from "../../api/statusListener";
import { DEFAULT_EXPECTED_S, deriveProgress, isTimedState } from "./progress";

const T0 = Date.parse("2026-11-24T10:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();
const MIN = 60_000;

function doc(over: Partial<SessionStatusDoc>): SessionStatusDoc {
  return {
    uid: "u",
    state: "transcribing",
    step: null,
    progress: 20,
    error_code: null,
    latest_report_version: null,
    updated_at: iso(T0),
    started_at: iso(T0 - 30_000),
    stage_started_at: iso(T0),
    waited_ms: 0,
    audio_s: 600,
    progress_next: 40,
    stage_expected_s: 100,
    transcript_ready: false,
    speaker_confirmed: false,
    rating_submitted: false,
    has_rating: false,
    ...over,
  };
}

describe("deriveProgress: timed stage", () => {
  it("is monotonic in t, below progress_next, <= 99, never below server progress", () => {
    const d = doc({});
    let prev = 0;
    for (let s = 0; s <= 20_000; s += 7) {
      const r = deriveProgress(d, T0 + s * 1000);
      expect(r.pct).toBeGreaterThanOrEqual(prev);
      expect(r.pct).toBeGreaterThanOrEqual(d.progress);
      expect(r.pct).toBeLessThan(40);
      expect(r.pct).toBeLessThanOrEqual(99);
      expect(Number.isInteger(r.pct)).toBe(true);
      prev = r.pct;
    }
  });

  it("matches the curve: floor(base + (next-1-base) * (1 - exp(-t/expected)))", () => {
    const r = deriveProgress(doc({}), T0 + 100_000);
    expect(r.pct).toBe(Math.floor(20 + 19 * (1 - Math.exp(-1))));
    expect(r.frozen).toBe(false);
    expect(r.hidden).toBe(false);
  });

  it("clamps a clock skew (now before stage start) to the base", () => {
    expect(deriveProgress(doc({}), T0 - 5000).pct).toBe(20);
  });

  it("caps at 99 on the last stage with progress_next 99", () => {
    const r = deriveProgress(doc({ state: "running", progress: 93, progress_next: 99 }), T0 + 1e9);
    expect(r.pct).toBeLessThanOrEqual(99);
    expect(r.pct).toBeGreaterThanOrEqual(93);
  });

  it("falls back to 99 as next when progress_next is missing", () => {
    const r = deriveProgress(doc({ progress_next: null }), T0 + 1e9);
    expect(r.pct).toBeLessThanOrEqual(99);
  });

  it("unknown audio_s and stage_expected_s use the default expected duration", () => {
    const r = deriveProgress(doc({ audio_s: null, stage_expected_s: null }), T0 + DEFAULT_EXPECTED_S * 1000);
    expect(r.pct).toBe(Math.floor(20 + 19 * (1 - Math.exp(-1))));
  });

  it("known audio_s without stage_expected_s uses clamp(20 + 0.2*audio_s, 30, 600)", () => {
    const r = deriveProgress(doc({ audio_s: 400, stage_expected_s: null }), T0 + 100_000);
    expect(r.pct).toBe(Math.floor(20 + 19 * (1 - Math.exp(-1))));
  });

  it("Elapsed = now - started_at - waited_ms", () => {
    const r = deriveProgress(doc({ waited_ms: 5000 }), T0 + 10_000);
    expect(r.elapsedMs).toBe(30_000 + 10_000 - 5000);
  });
});

describe("deriveProgress: upload", () => {
  const up = (over: Partial<SessionStatusDoc> = {}) =>
    doc({ state: "uploading", progress: 10, progress_next: 20, stage_expected_s: null, ...over });

  it("is base only with no byte counter", () => {
    expect(deriveProgress(up(), T0 + 5000).pct).toBe(10);
  });

  it("uses base plus the real byte fraction, below next", () => {
    expect(deriveProgress(up(), T0, 0.5).pct).toBe(15);
    expect(deriveProgress(up(), T0, 1).pct).toBeLessThan(20);
    expect(deriveProgress(up(), T0, 5).pct).toBeLessThan(20);
    expect(deriveProgress(up(), T0, -1).pct).toBe(10);
  });

  it("does not interpolate by time", () => {
    expect(deriveProgress(up(), T0 + 10 * MIN).pct).toBe(10);
  });

  it("created/upload_incomplete behave like uploading; Elapsed 0 before started_at", () => {
    const r = deriveProgress(up({ state: "created", started_at: null }), T0, 0.5);
    expect(r.pct).toBe(15);
    expect(r.elapsedMs).toBe(0);
    expect(deriveProgress(up({ state: "upload_incomplete" }), T0, 0.5).pct).toBe(15);
  });
});

describe("deriveProgress: frozen, final, hidden", () => {
  it("awaiting_input freezes pct and Elapsed for 10 simulated minutes", () => {
    const d = doc({ state: "awaiting_input", progress: 40, progress_next: 45, stage_started_at: iso(T0), started_at: iso(T0 - 60_000) });
    const first = deriveProgress(d, T0);
    expect(first.pct).toBe(40);
    expect(first.frozen).toBe(true);
    for (let m = 1; m <= 10; m++) {
      const r = deriveProgress(d, T0 + m * MIN);
      expect(r.pct).toBe(40);
      expect(r.elapsedMs).toBe(first.elapsedMs);
      expect(r.frozen).toBe(true);
    }
    expect(first.elapsedMs).toBe(60_000);
  });

  it("report_ready is 100 and frozen", () => {
    const r = deriveProgress(doc({ state: "report_ready", progress: 100, updated_at: iso(T0 + 5000) }), T0 + 10 * MIN);
    expect(r.pct).toBe(100);
    expect(r.frozen).toBe(true);
    expect(r.hidden).toBe(false);
    expect(r.elapsedMs).toBe(35_000);
  });

  it.each(["failed", "cancelled"] as const)("%s is hidden", (state) => {
    expect(deriveProgress(doc({ state }), T0).hidden).toBe(true);
  });

  it("never exceeds 99 before report_ready, for every timed state", () => {
    for (const state of ["validating", "transcribing", "running"] as const) {
      expect(isTimedState(state)).toBe(true);
      expect(deriveProgress(doc({ state, progress: 98, progress_next: 120 }), T0 + 1e9).pct).toBeLessThanOrEqual(99);
    }
    expect(isTimedState("awaiting_input")).toBe(false);
    expect(isTimedState("uploading")).toBe(false);
  });
});
