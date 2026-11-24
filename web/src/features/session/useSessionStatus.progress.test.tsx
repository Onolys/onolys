import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryStatusEmitter, setStatusListener, type SessionStatusDoc } from "../../api/statusListener";
import { failureView } from "../../api/errors";
import { deriveProgress } from "./progress";
import { FALLBACK_POLL_MS, useProgress, useSessionStatus, type StatusView } from "./useSessionStatus";

const get = vi.fn();
vi.mock("../../auth/useApiClient", () => {
  const client = { GET: (...a: unknown[]) => get(...a) };
  return { useApiClient: () => client };
});

const NOW = Date.parse("2026-11-24T10:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();
const emitter = createMemoryStatusEmitter();
const quiet = { current: false };
let queryClient: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
const mount = () => renderHook(() => useSessionStatus("s1", quiet), { wrapper });
const docOf = (state: SessionStatusDoc["state"], over: Partial<SessionStatusDoc> = {}): SessionStatusDoc => ({
  uid: "u",
  state,
  step: null,
  progress: 20,
  error_code: null,
  latest_report_version: null,
  updated_at: iso(NOW - 120_000),
  started_at: iso(NOW - 180_000),
  stage_started_at: iso(NOW - 120_000),
  waited_ms: 0,
  audio_s: 600,
  progress_next: 40,
  stage_expected_s: 140,
  transcript_ready: false,
  speaker_confirmed: false,
  rating_submitted: false,
  has_rating: false,
  ...over,
});
const detailOf = (d: SessionStatusDoc) => ({
  id: "s1",
  status: d.state,
  step: d.step,
  progress: d.progress,
  latest_report_version: null,
  updated_at: d.updated_at,
  started_at: d.started_at,
  stage_started_at: d.stage_started_at,
  waited_ms: d.waited_ms,
  audio_s: d.audio_s,
  progress_next: d.progress_next,
  stage_expected_s: d.stage_expected_s,
  flags: { transcript_ready: false, speaker_confirmed: false, rating_submitted: false, has_rating: false },
});
const docFrom = (v: StatusView) => {
  if (v.phase !== "live" && v.phase !== "fallback") throw new Error(`phase ${v.phase}`);
  return v.doc;
};

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  get.mockReset();
  emitter.clear();
  setStatusListener(emitter);
});
afterEach(() => vi.useRealTimers());

describe("useSessionStatus: progress", () => {
  it("a reload mid-transcription keeps Elapsed (from started_at, not first-seen)", () => {
    const { result } = mount(); // fresh mount = reload
    act(() => emitter.emit("s1", docOf("transcribing")));
    const p = deriveProgress(docFrom(result.current), NOW);
    expect(p.elapsedMs).toBe(180_000);
    expect(p.pct).toBeGreaterThanOrEqual(20);
  });

  it("running: runStartedAt comes from started_at after a reload", () => {
    const { result } = mount();
    act(() => emitter.emit("s1", docOf("running", { progress: 45, progress_next: 85 })));
    expect(result.current.phase === "live" && result.current.runStartedAt).toBe(NOW - 180_000);
  });

  it("a fallback-poll doc behaves the same (real updated_at, same Elapsed)", async () => {
    const { result } = mount();
    act(() => emitter.emitError("s1", new Error("down")));
    get.mockResolvedValue({ data: detailOf(docOf("transcribing")), response: { ok: true } });
    await act(async () => void (await vi.advanceTimersByTimeAsync(1)));
    await act(async () => void (await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS)));
    expect(result.current.phase).toBe("fallback");
    const doc = docFrom(result.current);
    expect(doc.updated_at).toBe(iso(NOW - 120_000));
    expect(deriveProgress(doc, NOW).elapsedMs).toBe(180_000);
  });

  it("fallback poll maps error_kind, retries_left and counted so the failure card still decides", async () => {
    const poll = async (over: Record<string, unknown>) => {
      queryClient.clear();
      const { result } = mount();
      act(() => emitter.emitError("s1", new Error("down")));
      get.mockResolvedValue({
        data: { ...detailOf(docOf("failed")), error: { code: "x" }, ...over },
        response: { ok: true },
      });
      await act(async () => void (await vi.advanceTimersByTimeAsync(1)));
      await act(async () => void (await vi.advanceTimersByTimeAsync(FALLBACK_POLL_MS)));
      expect(result.current.phase).toBe("fallback");
      return docFrom(result.current);
    };
    expect(failureView(await poll({ error_kind: "transient", retries_left: 2 })).action).toBe("retry");
    const uf = failureView(await poll({ error_kind: "user_file", retries_left: 0, counted: true }));
    expect(uf.action).toBe("upload_different");
    expect(uf.note).toBe("This counted toward your limit.");
    expect((await poll({ status: "cancelled", counted: true })).counted).toBe(true);
  });

  it("a late lower doc in the same state cannot move the bar back", () => {
    const { result } = mount();
    act(() => emitter.emit("s1", docOf("transcribing", { progress: 30 })));
    act(() => emitter.emit("s1", docOf("transcribing", { progress: 20 })));
    expect(docFrom(result.current).progress).toBe(30);
    expect(deriveProgress(docFrom(result.current), NOW).pct).toBeGreaterThanOrEqual(30);
  });

  it("a new state starts from its own server progress (re-run restarts lower)", () => {
    const { result } = mount();
    act(() => emitter.emit("s1", docOf("report_ready", { progress: 100 })));
    act(() => emitter.emit("s1", docOf("running", { progress: 45 })));
    expect(docFrom(result.current).progress).toBe(45);
  });
});

describe("useProgress", () => {
  it("ticks only while a timed state is active", () => {
    const timed = renderHook(({ d }) => useProgress(d), { initialProps: { d: docOf("transcribing", { stage_started_at: iso(NOW) }) } });
    const before = timed.result.current!.pct;
    act(() => void vi.advanceTimersByTime(60_000));
    expect(timed.result.current!.pct).toBeGreaterThan(before);
    timed.rerender({ d: docOf("awaiting_input", { progress: 40 }) });
    expect(vi.getTimerCount()).toBe(0);
    const frozen = timed.result.current!;
    act(() => void vi.advanceTimersByTime(10 * 60_000));
    expect(timed.result.current).toEqual(frozen);
  });

  it("Elapsed advances during uploading (once started_at is set) while the % stays on the byte fraction", () => {
    const d = docOf("uploading", { progress: 5, progress_next: 10, started_at: iso(NOW), stage_started_at: iso(NOW) });
    const up = renderHook(() => useProgress(d, 0));
    expect(up.result.current!.elapsedMs).toBe(0);
    act(() => void vi.advanceTimersByTime(5_000));
    expect(up.result.current!.elapsedMs).toBe(5_000);
    expect(up.result.current!.pct).toBe(5);
  });
});
