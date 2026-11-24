import { beforeEach, describe, expect, it, vi } from "vitest";

const fs = vi.hoisted(() => {
  const state = {
    next: undefined as ((s: unknown) => void) | undefined,
    error: undefined as ((e: Error) => void) | undefined,
    unsub: vi.fn(),
  };
  return {
    state,
    initializeFirestore: vi.fn<(app: unknown, opts: unknown, db: unknown) => unknown>(() => ({ kind: "db" })),
    memoryLocalCache: vi.fn(() => ({ kind: "memory" })),
    connectFirestoreEmulator: vi.fn(),
    doc: vi.fn((_db: unknown, col: string, id: string) => ({ path: `${col}/${id}` })),
    onSnapshot: vi.fn((_ref: unknown, next: (s: unknown) => void, error: (e: Error) => void) => {
      state.next = next;
      state.error = error;
      return state.unsub;
    }),
  };
});

vi.mock("firebase/app", () => ({ getApp: () => ({ name: "[DEFAULT]" }) }));
vi.mock("firebase/firestore", () => ({
  initializeFirestore: fs.initializeFirestore,
  memoryLocalCache: fs.memoryLocalCache,
  connectFirestoreEmulator: fs.connectFirestoreEmulator,
  doc: fs.doc,
  onSnapshot: fs.onSnapshot,
}));

import { failureView } from "./errors";
import { createFirestoreStatusListener, resetFirestoreForTests } from "./firestoreListener";
import type { SessionStatusDoc } from "./statusListener";
import { detailToDoc } from "../features/session/useSessionStatus";

const snap = (data: Record<string, unknown> | null) => ({ exists: () => data !== null, data: () => data });
const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  vi.clearAllMocks();
  fs.state.next = fs.state.error = undefined;
  resetFirestoreForTests();
});

describe("firestore status listener", () => {
  it("opens the configured database with a memory cache and listens on session_status/{id}", async () => {
    const l = createFirestoreStatusListener({ database: "staging" });
    l.subscribe("s1", vi.fn(), vi.fn());
    await flush();
    expect(fs.initializeFirestore).toHaveBeenCalledWith({ name: "[DEFAULT]" }, { localCache: { kind: "memory" } }, "staging");
    expect(fs.doc).toHaveBeenCalledWith({ kind: "db" }, "session_status", "s1");
    expect(fs.connectFirestoreEmulator).not.toHaveBeenCalled();
  });

  it("uses the (default) database when none is configured", async () => {
    createFirestoreStatusListener({}).subscribe("s1", vi.fn(), vi.fn());
    await flush();
    expect(fs.initializeFirestore.mock.calls[0][2]).toBe("(default)");
  });

  it("connects to the emulator host:port when configured, once", async () => {
    const l = createFirestoreStatusListener({ database: "(default)", emulator: "127.0.0.1:8080" });
    l.subscribe("s1", vi.fn(), vi.fn());
    l.subscribe("s2", vi.fn(), vi.fn());
    await flush();
    expect(fs.connectFirestoreEmulator).toHaveBeenCalledTimes(1);
    expect(fs.connectFirestoreEmulator).toHaveBeenCalledWith({ kind: "db" }, "127.0.0.1", 8080);
    expect(fs.initializeFirestore).toHaveBeenCalledTimes(1);
  });

  const ts = (iso: string) => ({ toDate: () => new Date(iso) });
  const base = {
    uid: "u1",
    step: null,
    progress: 0,
    error_code: null,
    latest_report_version: null,
    transcript_ready: false,
    speaker_confirmed: false,
    rating_submitted: false,
    has_rating: false,
    updated_at: "2026-01-02T03:04:05.000Z",
  };
  const cases: { name: string; raw: Record<string, unknown>; expected: Record<string, unknown> }[] = [
    {
      name: "failed transient with retries left",
      raw: {
        ...base,
        state: "failed",
        progress: 45,
        error_code: "stt_timeout",
        error_kind: "transient",
        retries_left: 2,
        counted: false,
        started_at: ts("2026-01-02T03:00:00.000Z"),
        stage_started_at: ts("2026-01-02T03:04:00.000Z"),
        updated_at: ts("2026-01-02T03:04:05.000Z"),
        waited_ms: 0,
        audio_s: 61.5,
      },
      expected: {
        ...base,
        state: "failed",
        progress: 45,
        error_code: "stt_timeout",
        error_kind: "transient",
        retries_left: 2,
        counted: false,
        started_at: "2026-01-02T03:00:00.000Z",
        stage_started_at: "2026-01-02T03:04:00.000Z",
        waited_ms: 0,
        audio_s: 61.5,
        progress_next: null,
        stage_expected_s: null,
      },
    },
    {
      name: "failed user_file counted, retries 0",
      raw: { ...base, state: "failed", error_code: "audio_too_short", error_kind: "user_file", retries_left: 0, counted: true },
      expected: {
        ...base,
        state: "failed",
        error_code: "audio_too_short",
        error_kind: "user_file",
        retries_left: 0,
        counted: true,
        started_at: null,
        stage_started_at: null,
        waited_ms: 0,
        audio_s: null,
        progress_next: null,
        stage_expected_s: null,
      },
    },
    {
      name: "failed permanent_internal",
      raw: { ...base, state: "failed", error_code: "internal", error_kind: "permanent_internal", retries_left: 0, counted: null },
      expected: {
        ...base,
        state: "failed",
        error_code: "internal",
        error_kind: "permanent_internal",
        retries_left: 0,
        counted: null,
        started_at: null,
        stage_started_at: null,
        waited_ms: 0,
        audio_s: null,
        progress_next: null,
        stage_expected_s: null,
      },
    },
    {
      name: "uploading with progress_next",
      raw: { ...base, state: "uploading", progress: 5, progress_next: 10, stage_expected_s: 30, started_at: ts("2026-01-02T03:04:00.000Z") },
      expected: {
        ...base,
        state: "uploading",
        progress: 5,
        error_kind: null,
        retries_left: null,
        counted: null,
        started_at: "2026-01-02T03:04:00.000Z",
        stage_started_at: null,
        waited_ms: 0,
        audio_s: null,
        progress_next: 10,
        stage_expected_s: 30,
      },
    },
    {
      name: "running with stage timing, waited and flags",
      raw: {
        ...base,
        state: "running",
        step: "tips",
        progress: 70,
        progress_next: 99,
        stage_expected_s: 40,
        waited_ms: 12000,
        audio_s: 300,
        latest_report_version: 1,
        started_at: ts("2026-01-02T03:00:00.000Z"),
        stage_started_at: ts("2026-01-02T03:04:00.000Z"),
        transcript_ready: true,
        speaker_confirmed: true,
        rating_submitted: true,
      },
      expected: {
        ...base,
        state: "running",
        step: "tips",
        progress: 70,
        error_kind: null,
        retries_left: null,
        counted: null,
        latest_report_version: 1,
        started_at: "2026-01-02T03:00:00.000Z",
        stage_started_at: "2026-01-02T03:04:00.000Z",
        waited_ms: 12000,
        audio_s: 300,
        progress_next: 99,
        stage_expected_s: 40,
        transcript_ready: true,
        speaker_confirmed: true,
        rating_submitted: true,
      },
    },
  ];

  it.each(cases)("maps a $name snapshot to a complete status doc (Timestamp -> ISO)", async ({ raw, expected }) => {
    const onStatus = vi.fn();
    createFirestoreStatusListener({}).subscribe("s1", onStatus, vi.fn());
    await flush();
    fs.state.next!(snap(raw));
    expect(onStatus).toHaveBeenLastCalledWith(expected);
  });

  it("maps a missing doc to null", async () => {
    const onStatus = vi.fn();
    createFirestoreStatusListener({}).subscribe("s1", onStatus, vi.fn());
    await flush();
    fs.state.next!(snap(null));
    expect(onStatus).toHaveBeenLastCalledWith(null);
  });

  it.each(cases)("live and REST mappers agree for $name (same doc, same failureView)", async ({ raw }) => {
    const onStatus = vi.fn();
    createFirestoreStatusListener({}).subscribe("s1", onStatus, vi.fn());
    await flush();
    fs.state.next!(snap(raw));
    const live = onStatus.mock.calls.at(-1)![0] as SessionStatusDoc;
    const iso = (v: unknown) => (v && typeof v === "object" ? (v as { toDate(): Date }).toDate().toISOString() : v);
    const rest = detailToDoc({
      status: raw.state,
      step: raw.step,
      progress: raw.progress,
      error: raw.error_code ? { code: raw.error_code } : null,
      error_kind: raw.error_kind,
      retries_left: raw.retries_left,
      counted: raw.counted,
      latest_report_version: raw.latest_report_version,
      updated_at: iso(raw.updated_at),
      started_at: iso(raw.started_at),
      stage_started_at: iso(raw.stage_started_at),
      waited_ms: raw.waited_ms,
      audio_s: raw.audio_s,
      progress_next: raw.progress_next,
      stage_expected_s: raw.stage_expected_s,
      flags: {
        transcript_ready: raw.transcript_ready,
        speaker_confirmed: raw.speaker_confirmed,
        rating_submitted: raw.rating_submitted,
        has_rating: raw.has_rating,
      },
    } as unknown as Parameters<typeof detailToDoc>[0]);
    expect({ ...live, uid: "" }).toEqual(rest); // REST detail carries no uid
    expect(failureView(live)).toEqual(failureView(rest));
    if (raw.error_kind === "transient") expect(failureView(live).action).toBe("retry");
    if (raw.error_kind === "user_file") expect(failureView(live).action).toBe("upload_different");
  });

  it("forwards listener errors such as permission-denied", async () => {
    const onError = vi.fn();
    createFirestoreStatusListener({}).subscribe("s1", vi.fn(), onError);
    await flush();
    const err = Object.assign(new Error("denied"), { code: "permission-denied" });
    fs.state.error!(err);
    expect(onError).toHaveBeenCalledWith(err);
  });

  it("unsubscribes the Firestore listener, including when leaving before it attached", async () => {
    const off = createFirestoreStatusListener({}).subscribe("s1", vi.fn(), vi.fn());
    await flush();
    off();
    expect(fs.state.unsub).toHaveBeenCalledTimes(1);

    const early = createFirestoreStatusListener({}).subscribe("s2", vi.fn(), vi.fn());
    early(); // before the lazy import resolved
    await flush();
    expect(fs.onSnapshot).toHaveBeenCalledTimes(1); // never attached for s2
  });

  it("reports a load failure through onError", async () => {
    fs.initializeFirestore.mockImplementationOnce(() => {
      throw new Error("boom");
    });
    const onError = vi.fn();
    createFirestoreStatusListener({}).subscribe("s1", vi.fn(), onError);
    await flush();
    expect(onError).toHaveBeenCalledTimes(1);
  });
});
