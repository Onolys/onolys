import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createMemoryStatusEmitter,
  setStatusListener,
  type SessionStatusDoc,
} from "../../api/statusListener";
import { RESUBSCRIBE_DELAYS_MS, useSessionStatus } from "./useSessionStatus";

const get = vi.fn();
vi.mock("../../auth/useApiClient", () => {
  const client = { GET: (...a: unknown[]) => get(...a) };
  return { useApiClient: () => client };
});

const MIN = 60_000;
const emitter = createMemoryStatusEmitter();
const doc = (state: SessionStatusDoc["state"], updated_at = new Date().toISOString()): SessionStatusDoc => ({
  uid: "u",
  state,
  step: null,
  progress: 10,
  error_code: null,
  latest_report_version: null,
  updated_at,
  transcript_ready: false,
  speaker_confirmed: false,
  rating_submitted: false,
  has_rating: false,
});
const quiet = { current: false };
let queryClient: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
const mount = () => renderHook(() => useSessionStatus("s1", quiet), { wrapper });
const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-20T10:00:00Z"));
  get.mockReset();
  get.mockResolvedValue({ data: {}, response: { ok: true } });
  emitter.clear();
  setStatusListener(emitter);
});
afterEach(() => vi.useRealTimers());

describe("useSessionStatus: stale transcribing nudge", () => {
  it("makes no call before 6 min, one at the threshold, then at most one per 60 s", () => {
    mount();
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(6 * MIN - 1);
    expect(get).not.toHaveBeenCalled();
    advance(1);
    expect(get).toHaveBeenCalledTimes(1);
    expect(get.mock.calls[0]![0]).toBe("/sessions/{id}");
    advance(MIN - 1);
    expect(get).toHaveBeenCalledTimes(1);
    advance(1);
    expect(get).toHaveBeenCalledTimes(2);
    advance(3 * MIN);
    expect(get).toHaveBeenCalledTimes(5);
  });

  it("counts from the doc's updated_at: an already-old doc nudges at once", () => {
    mount();
    act(() => emitter.emit("s1", doc("transcribing", new Date(Date.now() - 7 * MIN).toISOString())));
    advance(0);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("a fresh updated_at (progress) pushes the first nudge out", () => {
    mount();
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(5 * MIN);
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(5 * MIN);
    expect(get).not.toHaveBeenCalled();
    advance(MIN);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("stops when the state changes", () => {
    mount();
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(6 * MIN);
    expect(get).toHaveBeenCalledTimes(1);
    act(() => emitter.emit("s1", doc("failed")));
    advance(10 * MIN);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("stops on unmount", () => {
    const { unmount } = mount();
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(6 * MIN);
    unmount();
    advance(10 * MIN);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("ignores a failing call and keeps nudging", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    get.mockRejectedValue(new Error("boom"));
    mount();
    act(() => emitter.emit("s1", doc("transcribing")));
    advance(6 * MIN);
    await act(async () => void (await Promise.resolve()));
    advance(MIN);
    expect(get).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });
  it.each([
    ["created", 16],
    ["uploading", 16],
    ["validating", 23],
    ["running", 23],
  ] as const)("M-3: %s nudges at its server threshold (%i min), then at most once per 60 s", (state, min) => {
    mount();
    act(() => emitter.emit("s1", doc(state)));
    advance(min * MIN - 1);
    expect(get).not.toHaveBeenCalled();
    advance(1);
    expect(get).toHaveBeenCalledTimes(1);
    advance(MIN - 1);
    expect(get).toHaveBeenCalledTimes(1);
    advance(1);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("M-3: counts from stage_started_at when the doc has it", () => {
    mount();
    const started = new Date(Date.now() - 30 * MIN).toISOString();
    act(() => emitter.emit("s1", { ...doc("running"), stage_started_at: started }));
    advance(0);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it.each(["awaiting_input", "upload_incomplete", "report_ready", "failed"] as const)("never nudges for %s", (state) => {
    mount();
    act(() => emitter.emit("s1", doc(state)));
    advance(60 * MIN);
    expect(get).not.toHaveBeenCalled();
  });
});

describe("useSessionStatus: updates held back while quiet (drop)", () => {
  afterEach(() => {
    quiet.current = false;
  });

  it("replays the latest held doc once quiet clears (a failed DELETE)", () => {
    const { result } = mount();
    act(() => emitter.emit("s1", doc("awaiting_input")));
    expect(result.current).toMatchObject({ phase: "live", doc: { state: "awaiting_input" } });
    quiet.current = true; // DELETE in flight
    act(() => emitter.emit("s1", doc("running")));
    act(() => emitter.emit("s1", doc("report_ready")));
    advance(2_000);
    expect(result.current).toMatchObject({ doc: { state: "awaiting_input" } }); // still held back
    quiet.current = false; // DELETE failed
    advance(1_000);
    expect(result.current).toMatchObject({ phase: "live", doc: { state: "report_ready" } });
  });

  it("replays a held listener error as a drop (fallback) once quiet clears", async () => {
    get.mockResolvedValue({ data: { status: "awaiting_input", progress: 50, flags: {} }, response: { ok: true } });
    const { result } = mount();
    act(() => emitter.emit("s1", doc("awaiting_input")));
    quiet.current = true;
    act(() => emitter.emitError("s1", new Error("blip")));
    advance(1_000);
    expect(result.current.phase).toBe("live");
    quiet.current = false;
    advance(1_000);
    await act(async () => void (await vi.advanceTimersByTimeAsync(0)));
    expect(result.current.phase).toBe("fallback");
  });
});

const detail = { status: "awaiting_input", progress: 50, flags: { transcript_ready: true } };
const flush = () => act(async () => void (await vi.advanceTimersByTimeAsync(0)));

describe("useSessionStatus: listener drop (W16, AR2, D7)", () => {
  it("polls the detail while down, resubscribes with backoff, and goes live again", async () => {
    get.mockResolvedValue({ data: detail, response: { ok: true } });
    const subscribe = vi.spyOn(emitter, "subscribe");
    const { result } = mount();
    act(() => emitter.emit("s1", doc("awaiting_input")));
    act(() => emitter.emitError("s1", new Error("blip")));
    await flush();
    expect(result.current.phase).toBe("fallback");
    expect(subscribe).toHaveBeenCalledTimes(1);
    advance(1_000); // first resubscribe: the emitter replays the doc, so the listener is live again
    expect(subscribe).toHaveBeenCalledTimes(2);
    expect(result.current.phase).toBe("live");
    const calls = get.mock.calls.length;
    advance(20_000);
    expect(get.mock.calls.length).toBe(calls); // polling stopped
  });

  it("after the last retry keeps polling and reports exhausted; unmount stops it", async () => {
    get.mockResolvedValue({ data: detail, response: { ok: true } });
    const subscribe = vi.spyOn(emitter, "subscribe");
    const { result, unmount } = mount();
    for (let i = 0; i <= RESUBSCRIBE_DELAYS_MS.length; i++) {
      act(() => emitter.emitError("s1", new Error("down")));
      await flush();
      advance(16_000);
    }
    expect(subscribe).toHaveBeenCalledTimes(1 + RESUBSCRIBE_DELAYS_MS.length);
    expect(result.current).toMatchObject({ phase: "fallback", exhausted: true });
    const calls = get.mock.calls.length;
    await act(async () => void (await vi.advanceTimersByTimeAsync(5_100)));
    expect(get.mock.calls.length).toBeGreaterThan(calls);
    unmount();
    const after = get.mock.calls.length;
    advance(30_000);
    expect(get.mock.calls.length).toBe(after);
  });
});
