import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryStatusEmitter, type SessionStatusDoc } from "../api/statusListener";
import type { SessionState } from "../api/types";
import { MockBackend, MockHttpError, type CapsOverride } from "./stateMachine";

const U = "u1";
const MP3 = { content_type: "audio/mpeg", size_bytes: 1_000_000, filename_ext: "mp3" };
const CARD = { change_goal: "Walk more in the evenings" };
const SCORED = {
  change_goal: "Walk more in the evenings",
  globals: { cct: { score: 4, reason: "Because" } },
};

function make(opts: { caps?: CapsOverride } = {}) {
  const emitter = createMemoryStatusEmitter();
  const backend = new MockBackend({ emitter, ...opts });
  const history: SessionStatusDoc[] = [];
  return { emitter, backend, history };
}

/** create -> upload -> complete (state validating). */
function started(b: MockBackend, title?: string, uid = U): string {
  const { session } = b.createSession(uid, { title });
  b.requestAudio(uid, session.id, MP3);
  b.completeAudio(uid, session.id);
  return session.id;
}

function status(b: MockBackend, sid: string, uid = U) {
  return b.getSession(uid, sid);
}

function docOf(emitter: ReturnType<typeof createMemoryStatusEmitter>, sid: string): SessionStatusDoc {
  let doc: SessionStatusDoc | null = null;
  emitter.subscribe(sid, (d) => (doc = d), () => {})();
  if (!doc) throw new Error("no status doc");
  return doc;
}

function expectHttp(fn: () => unknown, status: number, code: string) {
  try {
    fn();
    expect.unreachable("expected MockHttpError");
  } catch (e) {
    expect(e).toBeInstanceOf(MockHttpError);
    expect((e as MockHttpError).status).toBe(status);
    expect((e as MockHttpError).code).toBe(code);
  }
}

let ctx: ReturnType<typeof make>;
beforeEach(() => {
  ctx = make();
});

describe("per-stage start time", () => {
  it("each run stage restarts stage_started_at (so the web interpolates inside the stage)", () => {
    let t = Date.parse("2026-11-24T10:00:00Z");
    const emitter = createMemoryStatusEmitter();
    const backend = new MockBackend({ emitter, now: () => new Date(t) });
    const sid = started(backend);
    backend.advance(sid);
    backend.advance(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    const codeStart = docOf(emitter, sid).stage_started_at;
    t += 60_000;
    backend.advance(sid); // -> tips
    const tips = docOf(emitter, sid);
    expect(tips.step).toBe("tips");
    expect(Date.parse(tips.stage_started_at!) - Date.parse(codeStart!)).toBe(60_000);
  });
});

describe("happy path walks every state", () => {
  it("created -> uploading -> validating -> transcribing -> awaiting_input -> running -> report_ready -> deleting", () => {
    const { backend, emitter } = ctx;
    const seen: (SessionState | "upload_failed")[] = [];
    const { session } = backend.createSession(U, {});
    const sid = session.id;
    emitter.subscribe(sid, (d) => d && seen.push(d.state), () => {});

    expect(status(backend, sid).status).toBe("created");
    backend.requestAudio(U, sid, MP3);
    expect(status(backend, sid).status).toBe("uploading");
    backend.completeAudio(U, sid);
    expect(status(backend, sid)).toMatchObject({ status: "validating", progress: 10 });

    backend.advance(sid);
    expect(status(backend, sid)).toMatchObject({ status: "transcribing", progress: 20 });

    backend.advance(sid);
    expect(status(backend, sid)).toMatchObject({
      status: "awaiting_input",
      progress: 40,
      flags: { transcript_ready: true, speaker_confirmed: false, rating_submitted: false },
    });

    backend.confirmSpeaker(U, sid, "spk_0");
    expect(status(backend, sid).status).toBe("awaiting_input");
    expect(status(backend, sid).flags.speaker_confirmed).toBe(true);

    backend.putRating(U, sid, { final: true, card: SCORED });
    expect(status(backend, sid)).toMatchObject({ status: "running", progress: 45, step: "code" });

    // progress and progress_next follow the server table (api progress.py): 45 + 40 + 8 + 3 = 96, last next is the 99 cap
    expect(docOf(emitter, sid)).toMatchObject({ progress: 45, progress_next: 85, stage_expected_s: 120 });
    const docs: SessionStatusDoc[] = [];
    emitter.subscribe(sid, (d) => d && docs.push(d), () => {});
    docs.length = 0;
    const progress: number[] = [];
    const steps: (string | null)[] = [];
    while (status(backend, sid).status === "running") {
      backend.advance(sid);
      progress.push(status(backend, sid).progress);
      steps.push(status(backend, sid).step ?? null);
    }
    expect(progress).toEqual([85, 93, 100]);
    expect(steps).toEqual(["tips", "assemble", null]);
    expect(docs.map((d) => [d.state, d.step, d.progress, d.progress_next])).toEqual([
      ["running", "tips", 85, 93],
      ["running", "assemble", 93, 99],
      ["running", "assemble", 96, 99],
      ["report_ready", null, 100, null],
    ]);
    expect(Math.max(...docs.filter((d) => d.state === "running").map((d) => d.progress_next ?? 0))).toBe(99);
    expect(status(backend, sid)).toMatchObject({
      status: "report_ready",
      latest_report_version: 1,
      progress: 100,
    });

    backend.deleteSession(U, sid);
    // first-occurrence order of the states a listener saw
    expect([...new Set(seen)]).toEqual([
      "created",
      "uploading",
      "validating",
      "transcribing",
      "awaiting_input",
      "running",
      "report_ready",
      "deleting",
    ]);
    expectHttp(() => backend.getSession(U, sid), 404, "not_found");
  });

  it("emits `failed` for a failing session (the ninth state)", () => {
    const { backend } = ctx;
    const sid = started(backend, "fail-no_speech");
    backend.settle(sid);
    expect(status(backend, sid).status).toBe("failed");
  });
});

describe("session_status mirror", () => {
  it("exists before createSession returns, with exactly the documented, PHI-free fields", () => {
    const { backend, emitter } = ctx;
    const { session } = backend.createSession(U, { title: "My private title" });
    const docs: SessionStatusDoc[] = [];
    emitter.subscribe(session.id, (d) => d && docs.push(d), () => {});
    expect(docs).toHaveLength(1);
    expect(Object.keys(docs[0]).sort()).toEqual(
      [
        "counted",
        "error_code",
        "error_kind",
        "has_rating",
        "latest_report_version",
        "progress",
        "progress_next",
        "rating_submitted",
        "retries_left",
        "speaker_confirmed",
        "stage_expected_s",
        "stage_started_at",
        "started_at",
        "state",
        "step",
        "transcript_ready",
        "uid",
        "updated_at",
        "waited_ms",
      ].sort(),
    );
    expect(JSON.stringify(docs[0])).not.toContain("My private title");
  });

  it("never lets progress decrease within a run", () => {
    const { backend, emitter } = ctx;
    const sid = started(backend);
    const progress: number[] = [];
    emitter.subscribe(sid, (d) => d && progress.push(d.progress), () => {});
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    for (let i = 1; i < progress.length; i++) expect(progress[i]).toBeGreaterThanOrEqual(progress[i - 1]);
    expect(progress.at(-1)).toBe(100);
  });
});

describe("first-run gate (any order, exactly one run)", () => {
  type Input = "rating" | "speaker" | "transcript";
  const orders: Input[][] = [
    ["rating", "transcript", "speaker"],
    ["transcript", "rating", "speaker"],
    ["transcript", "speaker", "rating"],
  ];
  it.each(orders)("%s, %s, %s", (...order) => {
    const { backend } = ctx;
    const sid = started(backend);
    // rating may arrive at any time, even before the transcript exists
    const apply = (i: Input) => {
      if (i === "rating") backend.putRating(U, sid, { final: true, card: SCORED });
      if (i === "speaker") backend.confirmSpeaker(U, sid, "spk_0");
      if (i === "transcript") backend.settle(sid);
    };
    order.forEach((i, idx) => {
      if (idx < 2) expect(status(backend, sid).status).not.toBe("running");
      apply(i);
    });
    expect(status(backend, sid).status).toBe("running");
    expect(backend.listRuns(U, sid)).toHaveLength(1);
  });

  it("accepts a rating while the file is still uploading and transcribing", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    backend.putRating(U, session.id, { final: true, card: CARD });
    expect(status(backend, session.id)).toMatchObject({
      status: "created",
      flags: { rating_submitted: true, has_rating: false },
    });
    backend.requestAudio(U, session.id, MP3);
    backend.completeAudio(U, session.id);
    backend.advance(session.id);
    expect(status(backend, session.id).status).toBe("transcribing");
    expectHttp(() => backend.putRating(U, session.id, { final: true, card: SCORED }), 409, "rating_final");
    expect(status(backend, session.id).flags.has_rating).toBe(false);
  });

  it("a draft never satisfies the gate", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: false, card: SCORED });
    expect(status(backend, sid)).toMatchObject({
      status: "awaiting_input",
      flags: { rating_submitted: false, has_rating: false },
    });
  });

  it.each([
    ["no_rating: true", { final: true, no_rating: true, card: CARD }, false],
    ["a final card with no scores/counts/notes", { final: true, card: CARD }, false],
    ["a final card with scores", { final: true, card: SCORED }, true],
    ["a final card with only notes", { final: true, card: { ...CARD, notes: "context" } }, true],
  ])("%s sets has_rating correctly", (_name, body, hasRating) => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    backend.putRating(U, session.id, body);
    expect(status(backend, session.id).flags).toMatchObject({
      rating_submitted: true,
      has_rating: hasRating,
    });
  });

  it("cannot confirm a speaker before the transcript is ready", () => {
    const { backend } = ctx;
    const sid = started(backend);
    expectHttp(() => backend.confirmSpeaker(U, sid, "spk_0"), 409, "invalid_state");
  });

  it("rejects an unknown speaker id", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    expectHttp(() => backend.confirmSpeaker(U, sid, "nobody"), 422, "invalid_parameters");
  });
});

describe("awaiting_input flags", () => {
  it("lists what is missing: speaker only, rating only, both", () => {
    const { backend } = ctx;
    const both = started(backend);
    backend.settle(both);
    expect(status(backend, both).flags).toEqual({
      transcript_ready: true,
      speaker_confirmed: false,
      rating_submitted: false,
      has_rating: false,
    });

    const noSpeaker = started(backend);
    backend.putRating(U, noSpeaker, { final: true, card: SCORED });
    backend.settle(noSpeaker);
    expect(status(backend, noSpeaker)).toMatchObject({
      status: "awaiting_input",
      flags: { speaker_confirmed: false, rating_submitted: true },
    });

    const noRating = started(backend);
    backend.settle(noRating);
    backend.confirmSpeaker(U, noRating, "spk_0");
    expect(status(backend, noRating)).toMatchObject({
      status: "awaiting_input",
      flags: { speaker_confirmed: true, rating_submitted: false },
    });
  });
});

describe("failure injection by title", () => {
  it.each([
    ["fail-audio_unreadable", "validate", "audio_unreadable"],
    ["fail-unsupported_audio", "validate", "unsupported_audio"],
    ["fail-no_speech", "transcribe", "no_speech"],
    ["fail-speakers_not_separated", "transcribe", "speakers_not_separated"],
    ["fail-transcription_failed", "transcribe", "transcription_failed"],
  ])("%s fails at %s with %s", (title, step, code) => {
    const { backend } = ctx;
    const sid = started(backend, title);
    backend.settle(sid);
    expect(status(backend, sid)).toMatchObject({
      status: "failed",
      error: { code, step },
      flags: { transcript_ready: false },
    });
    expectHttp(() => backend.startRun(U, sid, {}), 409, "invalid_state");
  });

  function ready(title: string) {
    const { backend } = ctx;
    const sid = started(backend, title);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    return { backend, sid };
  }

  it("fail-code fails the run and the session (can Try again)", () => {
    const { backend, sid } = ready("fail-code");
    expect(status(backend, sid)).toMatchObject({ status: "failed", error: { code: "internal_error", step: "code" } });
    expect(status(backend, sid).latest_report_version).toBeNull();
    backend.startRun(U, sid, {}); // a system failure offers Try again (same stored rating)
    expect(status(backend, sid)).toMatchObject({ status: "running", progress: 45 });
    expect(backend.listRuns(U, sid)[1].rating_id).toBe(backend.listRuns(U, sid)[0].rating_id);
  });

  it("the old fail-paudit / fail-eaudit markers are plain titles now (no failure, no reasons audit)", () => {
    for (const t of ["fail-paudit", "fail-eaudit"]) {
      const { backend, sid } = ready(t);
      expect(status(backend, sid).status).toBe("report_ready");
      expect(backend.getReport(U, sid, 1).warnings.map((w) => w.code)).not.toContain("reasons_audit_failed");
    }
  });

  it("walks code, tips, assemble only (weights 40/8/3) and the report names run_info.miti", () => {
    const { backend } = ctx;
    const sid = started(backend, "plain");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, no_rating: true, card: { change_goal: "Walk more" } });
    const steps: (string | null)[] = [];
    while (status(backend, sid).status === "running") {
      backend.advance(sid);
      steps.push(status(backend, sid).step ?? null);
    }
    expect(steps).toEqual(["tips", "assemble", null]);
    const r = backend.getReport(U, sid, 1);
    expect(Object.keys(r.run_info).sort()).toEqual(["evaluation", "miti"]);
    expect(r.header.has_clinician_rating).toBe(false);
  });

  it("fail-tips produces a report with no tips + warning", () => {
    const { backend, sid } = ready("fail-tips");
    const r = backend.getReport(U, sid, 1);
    expect(r.tips).toEqual([]);
    expect(r.warnings.map((w) => w.code)).toContain("tips_failed");
  });
});

describe("daily cap", () => {
  it("cap-held: auto-start is held (awaiting_input + error_code) and Start runs it", () => {
    const { backend } = ctx;
    const sid = started(backend, "cap-held");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    expect(status(backend, sid)).toMatchObject({
      status: "awaiting_input",
      error: { code: "daily_cap_reached" },
    });
    expect(backend.listRuns(U, sid)).toHaveLength(0);
    backend.startRun(U, sid, {});
    expect(status(backend, sid)).toMatchObject({ status: "running" });
    expect(status(backend, sid).error).toBeUndefined();
  });

  it("auto-start held by another running session reports concurrent_runs, not the daily cap (review R2)", () => {
    const { backend } = ctx;
    const first = started(backend);
    backend.settle(first);
    backend.confirmSpeaker(U, first, "spk_0");
    backend.putRating(U, first, { final: true, card: SCORED });
    expect(status(backend, first)).toMatchObject({ status: "running" });
    const second = started(backend);
    backend.settle(second);
    backend.confirmSpeaker(U, second, "spk_0");
    backend.putRating(U, second, { final: true, card: SCORED });
    expect(status(backend, second)).toMatchObject({ status: "awaiting_input", error: { code: "concurrent_runs" } });
    expect(backend.listRuns(U, second)).toHaveLength(0);
    expectHttp(() => backend.startRun(U, second, {}), 429, "concurrent_runs");
  });

  it("a real cap: POST /runs over the cap is 429 daily_cap_reached; usage reports it", () => {
    const { backend } = make({ caps: { eval: { day: 1 } } });
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expect(backend.getUsage(U).eval.day).toMatchObject({ used: 1, cap: 1 });
    const next = started(backend);
    backend.settle(next);
    backend.confirmSpeaker(U, next, "spk_0");
    expectHttp(() => backend.startRun(U, next, {}), 429, "daily_cap_reached");
  });

  it("the auto-start also stops at a real cap", () => {
    const { backend } = make({ caps: { eval: { day: 0 } } });
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    expect(status(backend, sid).error).toEqual({ code: "daily_cap_reached" });
  });
});

describe("free interview runs mirror the API (review round 2)", () => {
  /** An interview-linked session, ready except the final rating. */
  function interviewSession(backend: MockBackend, title?: string): string {
    const iv = backend.createInterview(U, { scenario_id: "sc_anxious_parent" });
    backend.setInterviewState(iv.interview_id, "ended", 60);
    const { session } = backend.createSession(U, { interview_id: iv.interview_id, title });
    backend.requestAudio(U, session.id, MP3);
    backend.completeAudio(U, session.id);
    backend.settle(session.id);
    backend.confirmSpeaker(U, session.id, "spk_0");
    return session.id;
  }

  it("an interview session at the eval cap auto-starts its first run without counting", () => {
    const { backend } = make({ caps: { eval: { day: 0 } } });
    const sid = interviewSession(backend);
    backend.putRating(U, sid, { final: true, card: SCORED });
    expect(status(backend, sid)).toMatchObject({ status: "running", free_run: true });
    expect(backend.getUsage(U).eval.day.used).toBe(0);
  });

  it("a failed free run: Try again at the cap succeeds without counting", () => {
    const { backend } = make({ caps: { eval: { day: 0 } } });
    const sid = interviewSession(backend, "fail-code");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expect(status(backend, sid)).toMatchObject({ status: "failed" });
    backend.startRun(U, sid, {});
    expect(status(backend, sid)).toMatchObject({ status: "running" });
    expect(backend.getUsage(U).eval.day.used).toBe(0);
  });

  it("a free first run still respects max 1 active run", () => {
    const { backend } = make({ caps: { eval: { day: 0 } } });
    const a = interviewSession(backend);
    backend.putRating(U, a, { final: true, card: SCORED });
    const b = interviewSession(backend);
    backend.putRating(U, b, { final: true, card: SCORED });
    expect(status(backend, b)).toMatchObject({ status: "awaiting_input", error: { code: "concurrent_runs" } });
  });

  it("a non-interview Try again at the cap is still 429 daily_cap_reached", () => {
    const { backend } = make({ caps: { eval: { day: 1 } } });
    const sid = started(backend, "fail-code");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expect(status(backend, sid)).toMatchObject({ status: "failed", free_run: false });
    expectHttp(() => backend.startRun(U, sid, {}), 429, "daily_cap_reached");
  });
});

describe("usage caps by kind and period", () => {
  function ready(backend: MockBackend): string {
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    return sid;
  }
  function awaiting(backend: MockBackend): string {
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    return sid;
  }
  const detail = (fn: () => unknown) => {
    try {
      fn();
    } catch (e) {
      return (e as MockHttpError).details[0];
    }
    return undefined;
  };

  it("getUsage returns per-kind day periods only, with reset times", () => {
    const { backend } = make({ caps: { eval: { day: 3 }, interview: { day: 2 } } });
    ready(backend);
    expect(backend.getUsage(U)).toEqual({
      eval: { day: { used: 1, cap: 3, resets_at: expect.stringMatching(/T00:00:00\.000Z$/) } },
      interview: { day: { used: 0, cap: 2, resets_at: expect.any(String) } },
    });
  });

  it("a second start while another session is running: 429 concurrent_runs", () => {
    const { backend } = make();
    const a = awaiting(backend);
    backend.startRun(U, a, {}); // a is now running
    const b = awaiting(backend);
    expectHttp(() => backend.startRun(U, b, {}), 429, "concurrent_runs");
  });

  it("eval day cap: 429 daily_cap_reached with period=day", () => {
    const { backend } = make({ caps: { eval: { day: 1 } } });
    ready(backend); // uses the one run
    const sid = awaiting(backend);
    expectHttp(() => backend.startRun(U, sid, {}), 429, "daily_cap_reached");
    expect(detail(() => backend.startRun(U, sid, {}))).toMatchObject({ period: "day" });
  });

  it("interview caps: 429 interview_cap_reached with the period, kinds do not share counters", () => {
    const { backend } = make({ caps: { interview: { day: 1 } } });
    backend.consumeInterview(U);
    expect(backend.getUsage(U).interview.day.used).toBe(1);
    expect(backend.getUsage(U).eval.day.used).toBe(0);
    expectHttp(() => backend.consumeInterview(U), 429, "interview_cap_reached");
    expect(detail(() => backend.consumeInterview(U))).toMatchObject({ period: "day" });
  });

  it("a refused attempt counts nothing", () => {
    const { backend } = make({ caps: { eval: { day: 1 } } });
    ready(backend);
    const sid = awaiting(backend);
    expect(() => backend.startRun(U, sid, {})).toThrow();
    expect(backend.getUsage(U).eval.day.used).toBe(1);
  });
});

describe("final ratings and report versions (FX45)", () => {
  function reported(rating: object) {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, rating as never);
    backend.settle(sid);
    return { backend, sid };
  }

  it("a ready report is final: POST /runs and a final PUT /rating are 409 rating_final", () => {
    const { backend, sid } = reported({ final: true, card: SCORED });
    expectHttp(() => backend.startRun(U, sid, {}), 409, "rating_final");
    expectHttp(() => backend.putRating(U, sid, { final: true, card: CARD }), 409, "rating_final");
    backend.putRating(U, sid, { final: false, card: CARD }); // a draft is only a draft
    expect(backend.listReports(U, sid).map((r) => r.version)).toEqual([1]);
    expect(backend.listRuns(U, sid)).toHaveLength(1);
    expect(status(backend, sid).latest_report_version).toBe(1);
  });

  it("a submitted rating is final before any report exists (FX45 follow-up)", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: CARD });
    expectHttp(() => backend.putRating(U, sid, { final: true, card: SCORED }), 409, "rating_final");
    backend.putRating(U, sid, { final: false, card: SCORED }); // a draft is only a draft
  });

  it("a no-rating report is final too", () => {
    const { backend, sid } = reported({ final: true, no_rating: true, card: CARD });
    const v1 = backend.getReport(U, sid, 1);
    expect(v1.header.has_clinician_rating).toBe(false);
    expect(v1.reasons_audit.status).toBe("skipped");
    expectHttp(() => backend.putRating(U, sid, { final: true, card: SCORED }), 409, "rating_final");
    expectHttp(() => backend.startRun(U, sid, {}), 409, "rating_final");
  });

  it("a bad-file failure is not retryable (invalid_state); a system failure is", () => {
    const { backend } = ctx;
    const sid = started(backend, "fail-code");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expect(status(backend, sid).error?.code).toBe("internal_error");
    backend.startRun(U, sid, {}); // internal_error: Try again
    const bad = started(backend, "fail-no_speech");
    backend.settle(bad);
    expectHttp(() => backend.startRun(U, bad, {}), 409, "invalid_state");
  });

  it("Try again ignores the client's preset and n_runs and reuses the failed run's", () => {
    const { backend } = ctx;
    const sid = started(backend, "fail-code");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    const [first] = backend.listRuns(U, sid);
    backend.startRun(U, sid, { preset: "fast", n_runs: 3 });
    const second = backend.listRuns(U, sid).at(-1)!;
    expect(second.run_id).not.toBe(first.run_id);
    expect([second.preset, second.n_runs]).toEqual([first.preset, first.n_runs]);
  });

  it("a transient failure carries kind + retries_left; retry moves it on and is capped at 3", () => {
    const { backend, emitter } = ctx;
    const sid = started(backend, "fail-transient");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    const docs: SessionStatusDoc[] = [];
    emitter.subscribe(sid, (d) => d && docs.push(d), () => {});
    expect(docs.at(-1)).toMatchObject({ error_code: "upstream_unavailable", error_kind: "transient", retries_left: 3 });
    for (let left = 2; left >= 0; left--) {
      backend.retrySession(U, sid);
      backend.settle(sid);
      expect(docs.at(-1)).toMatchObject({ error_kind: "transient", retries_left: left });
    }
    expectHttp(() => backend.retrySession(U, sid), 409, "invalid_state");
  });

  it("session detail carries kind + retries_left, and a transcribe retry clears sttSubmitted", () => {
    const { backend } = ctx;
    const sid = started(backend, "fail-transient");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expect(backend.getSession(U, sid)).toMatchObject({ error_kind: "transient", retries_left: 3 });
    const bad = started(backend, "fail-no_speech");
    backend.settle(bad);
    expect(backend.getSession(U, bad)).toMatchObject({ error_kind: "user_file", retries_left: 0, counted: false });
    // transcribe retry: the API's retry_step drops stt_operation, so the mock is not submitted again
    const t = started(backend, "fail-transient");
    const rec = (backend as unknown as { sessions: Map<string, { state: string; step: string | null; error: unknown; sttSubmitted: boolean }> }).sessions.get(t)!;
    rec.state = "failed";
    rec.step = "transcribe";
    rec.error = { code: "upstream_unavailable", step: "transcribe" };
    rec.sttSubmitted = true;
    backend.retrySession(U, t);
    expect(rec.sttSubmitted).toBe(false);
  });

  it("retry is 409 for a permanent or user_file failure; their docs carry the kind", () => {
    const { backend, emitter } = ctx;
    const sid = started(backend, "fail-code");
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    backend.settle(sid);
    expectHttp(() => backend.retrySession(U, sid), 409, "invalid_state");
    const bad = started(backend, "fail-no_speech");
    const docs: SessionStatusDoc[] = [];
    emitter.subscribe(bad, (d) => d && docs.push(d), () => {});
    backend.settle(bad);
    expect(docs.at(-1)).toMatchObject({ error_kind: "user_file", counted: false });
    expectHttp(() => backend.retrySession(U, bad), 409, "invalid_state");
  });

  it("fail-upload_failed leaves only an upload_failed status doc", () => {
    const { backend, emitter } = ctx;
    const sid = started(backend, "fail-upload_failed");
    const docs: SessionStatusDoc[] = [];
    emitter.subscribe(sid, (d) => d && docs.push(d), () => {});
    backend.settle(sid);
    expect(docs.at(-1)).toMatchObject({ state: "upload_failed", error_code: "audio_unreadable" });
    expectHttp(() => backend.getSession(U, sid), 404, "not_found");
  });

  it("run records carry stt, preset, code_version and the rating snapshot", () => {
    const { backend, sid } = reported({ final: true, card: SCORED });
    const [run] = backend.listRuns(U, sid);
    expect(run).toMatchObject({ status: "done", n_runs: 1 });
    expect(run.rating_id).toBeTruthy();
    expect(run.code_version).toBeTruthy();
    expect(run.stt?.provider).toBeTruthy();
    expect(backend.getRun(U, run.run_id).run_id).toBe(run.run_id);
  });

  it("a run while running is 409", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.startRun(U, sid, {});
    expectHttp(() => backend.startRun(U, sid, {}), 409, "invalid_state");
  });

  it("unknown report version is 404", () => {
    const { backend, sid } = reported({ final: true, card: SCORED });
    expectHttp(() => backend.getReport(U, sid, 9), 404, "not_found");
  });
});

describe("rating draft vs final", () => {
  it("GET returns the draft only when newer than the last final", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    const sid = session.id;
    expect(backend.getRating(U, sid)).toEqual({});
    backend.putRating(U, sid, { final: false, card: { change_goal: "draft goal" } });
    expect(backend.getRating(U, sid).draft?.card.change_goal).toBe("draft goal");
    expect(backend.getRating(U, sid).final).toBeUndefined();
    backend.putRating(U, sid, { final: true, card: CARD });
    expect(backend.getRating(U, sid).draft).toBeUndefined();
    expect(backend.getRating(U, sid).final?.card.change_goal).toBe(CARD.change_goal);
    backend.putRating(U, sid, { final: false, card: { change_goal: "newer" } });
    expect(backend.getRating(U, sid).draft?.card.change_goal).toBe("newer");
    expect(backend.getRating(U, sid).final).toBeDefined();
  });

  it("the final PUT is a new revision; a second final is 409 rating_final", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    const a = backend.putRating(U, session.id, { final: true, card: CARD });
    expect(a.rating_id).toBeTruthy();
    expectHttp(() => backend.putRating(U, session.id, { final: true, card: SCORED }), 409, "rating_final");
    expect(backend.getRating(U, session.id).final?.rating_id).toBe(a.rating_id);
  });

  it.each([
    ["reason > 1000", { final: true, card: { change_goal: "g", globals: { cct: { reason: "x".repeat(1001) } } } }, "globals.cct.reason"],
    ["example text > 1000", { final: true, card: { change_goal: "g", globals: { cct: { example: { at_s: 3, text: "x".repeat(1001) } } } } }, "globals.cct.example.text"],
    ["code note > 1000", { final: true, card: { change_goal: "g", counts: { sr: { note: "x".repeat(1001) } } } }, "counts.sr.note"],
    ["notes > 3000", { final: true, card: { change_goal: "g", notes: "x".repeat(3001) } }, "notes"],
    ["missing change_goal on final", { final: true, card: {} }, "change_goal"],
    ["score out of range", { final: true, card: { change_goal: "g", globals: { cct: { score: 6 } } } }, "globals.cct.score"],
  ])("final with %s is 422 rating_invalid naming the field", (_n, body, field) => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    try {
      backend.putRating(U, session.id, body as never);
      expect.unreachable();
    } catch (e) {
      const err = e as MockHttpError;
      expect(err.status).toBe(422);
      expect(err.details.every((d) => d.code === "rating_invalid")).toBe(true);
      expect(err.details.map((d) => d.field)).toContain(field.replaceAll(".", "/"));
      expect(err.details.every((d) => typeof d.issue === "string")).toBe(true);
    }
  });

  it("a draft over a hard limit is rejected too, but a draft without change_goal is fine", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    backend.putRating(U, session.id, { final: false, card: {} });
    expectHttp(
      () => backend.putRating(U, session.id, { final: false, card: { notes: "x".repeat(3001) } }),
      422,
      "rating_invalid",
    );
  });

  it("is rejected only in deleting (session is gone afterwards)", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    backend.deleteSession(U, session.id);
    expectHttp(() => backend.putRating(U, session.id, { final: true, card: CARD }), 404, "not_found");
  });
});

describe("validation of upload calls", () => {
  it.each([
    ["audio/mpeg", "mp3", "audio/mpeg"],
    ["audio/x-m4a", "m4a", "audio/mp4"],
    ["audio/mp4", "m4a", "audio/mp4"],
    ["", "m4a", "audio/mp4"],
    ["", "wav", "audio/wav"],
    ["audio/x-wav", "wav", "audio/wav"],
  ])("maps %j + .%s to canonical %s in required_headers", (content_type, filename_ext, canonical) => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    const r = backend.requestAudio(U, session.id, { content_type, size_bytes: 10, filename_ext });
    expect(r.required_headers["Content-Type"]).toBe(canonical);
    expect(r.required_headers["x-goog-content-length-range"]).toBe("0,314572800");
    expect(r.upload_url).toContain(r.upload_id);
  });

  it("upload_url is same-origin in a browser (the prod CSP connect-src has no mock host; prod uses storage.googleapis.com)", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    const r = backend.requestAudio(U, session.id, { content_type: "audio/mpeg", size_bytes: 10, filename_ext: "mp3" });
    expect(new URL(r.upload_url).origin).toBe(location.origin);
  });

  it("422 unsupported_audio for an unknown type and 422 audio_too_large over 300 MB", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    expectHttp(
      () => backend.requestAudio(U, session.id, { content_type: "video/mp4", size_bytes: 10, filename_ext: "mp4" }),
      422,
      "unsupported_audio",
    );
    expectHttp(
      () => backend.requestAudio(U, session.id, { ...MP3, size_bytes: 300 * 1024 * 1024 + 1 }),
      422,
      "audio_too_large",
    );
  });

  it("409 invalid_state: complete before audio, audio after validation started", () => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    expectHttp(() => backend.completeAudio(U, session.id), 409, "invalid_state");
    backend.requestAudio(U, session.id, MP3);
    backend.requestAudio(U, session.id, MP3); // fresh URL while still uploading is fine
    backend.completeAudio(U, session.id);
    expectHttp(() => backend.requestAudio(U, session.id, MP3), 409, "invalid_state");
  });

  it("409 invalid_state: transcript before transcription finishes", () => {
    const { backend } = ctx;
    const sid = started(backend);
    expectHttp(() => backend.getTranscript(U, sid), 409, "invalid_state");
  });
});

describe("transcript and speaker fixtures", () => {
  it("lists 3 sample lines per speaker; role is null until confirmed", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    const sp = backend.getSpeakers(U, sid);
    expect(sp.speakers.map((s) => s.speaker)).toEqual(["spk_0", "spk_1"]);
    for (const s of sp.speakers) expect(s.samples).toHaveLength(3);
    expect(backend.getTranscript(U, sid).turns.every((t) => t.role === null)).toBe(true);
    backend.confirmSpeaker(U, sid, "spk_0");
    const turns = backend.getTranscript(U, sid).turns;
    expect(turns.find((t) => t.speaker === "spk_0")?.role).toBe("clinician");
    expect(turns.find((t) => t.speaker === "spk_1")?.role).toBe("client");
  });

  it("three-speakers title yields a 3-speaker gate", () => {
    const { backend } = ctx;
    const sid = started(backend, "three-speakers");
    backend.settle(sid);
    const sp = backend.getSpeakers(U, sid);
    expect(sp.speakers).toHaveLength(3);
    for (const s of sp.speakers) expect(s.samples).toHaveLength(3);
  });

  it("utf8-edge title serves the UTF-8 edge transcript", () => {
    const { backend } = ctx;
    const sid = started(backend, "utf8-edge");
    backend.settle(sid);
    const text = backend.getTranscript(U, sid).turns.map((t) => t.text).join(" ");
    expect(text).toMatch(/\p{Extended_Pictographic}/u);
  });
});

describe("tenancy, list, delete, idempotency", () => {
  it("another user gets 404 on every id", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    expectHttp(() => backend.getSession("u2", sid), 404, "not_found");
    expectHttp(() => backend.getTranscript("u2", sid), 404, "not_found");
    expectHttp(() => backend.deleteSession("u2", sid), 404, "not_found");
    expectHttp(() => backend.putRating("u2", sid, { final: false, card: {} }), 404, "not_found");
    expect(backend.listSessions("u2", {}).items).toEqual([]);
  });

  it("lists newest first with cursor paging, in every state", () => {
    const { backend } = ctx;
    const ids = [1, 2, 3].map(() => backend.createSession(U, {}).session.id);
    const page1 = backend.listSessions(U, { limit: 2 });
    expect(page1.items.map((i) => i.id)).toEqual([ids[2], ids[1]]);
    expect(page1.next_cursor).toBeTruthy();
    const page2 = backend.listSessions(U, { limit: 2, cursor: page1.next_cursor ?? undefined });
    expect(page2.items.map((i) => i.id)).toEqual([ids[0]]);
    expect(page2.next_cursor).toBeUndefined();
    expect(page1.items[0]).toMatchObject({ status: "created", latest_report_version: null, error_code: null });
  });

  it("delete removes the session and its status doc", () => {
    const { backend, emitter } = ctx;
    const { session } = backend.createSession(U, {});
    let last: SessionStatusDoc | null | undefined;
    emitter.subscribe(session.id, (d) => (last = d), () => {});
    backend.deleteSession(U, session.id);
    expect(last).toBeNull();
    expect(backend.listSessions(U, {}).items).toEqual([]);
  });

  it("Idempotency-Key: same key+body returns the original; different body is 409 conflict", () => {
    const { backend } = ctx;
    const a = backend.createSession(U, { title: "a" }, "k1");
    const b = backend.createSession(U, { title: "a" }, "k1");
    expect(b.session.id).toBe(a.session.id);
    expect(backend.listSessions(U, {}).items).toHaveLength(1);
    expectHttp(() => backend.createSession(U, { title: "different" }, "k1"), 409, "conflict");
  });

  it("validates create params", () => {
    const { backend } = ctx;
    expectHttp(() => backend.createSession(U, { n_runs: 9 }), 422, "invalid_parameters");
    expectHttp(() => backend.createSession(U, { preset: "nope" }), 422, "invalid_parameters");
  });
});

describe("cancelSession (04-cancel R2/R4)", () => {
  const usedEval = (b: MockBackend) => b.getUsage(U).eval.day.used;

  it.each(["created", "uploading", "validating"] as const)("an early state (%s) is cancelled without a charge", (state) => {
    const { backend } = ctx;
    const { session } = backend.createSession(U, {});
    const sid = session.id;
    if (state !== "created") backend.requestAudio(U, sid, MP3);
    if (state === "validating") backend.completeAudio(U, sid);
    expect(status(backend, sid).status).toBe(state);
    expect(backend.cancelSession(U, sid)).toEqual({ counted: false });
    expect(status(backend, sid)).toMatchObject({ status: "cancelled", counted: false, cancel: { counted: false, units: 0 } });
    expect(usedEval(backend)).toBe(0);
  });

  it("transcribing without an STT job is free; with the job submitted it counts once", () => {
    const { backend } = ctx;
    const free = started(backend);
    backend.advance(free); // validating -> transcribing
    expect(status(backend, free).status).toBe("transcribing");
    expect(backend.cancelSession(U, free)).toEqual({ counted: false });
    const paid = started(backend);
    backend.advance(paid);
    backend.submitStt(paid);
    expect(backend.cancelSession(U, paid)).toEqual({ counted: true });
    expect(status(backend, paid).cancel).toMatchObject({ counted: true, units: 1 });
    expect(usedEval(backend)).toBe(1);
  });

  it("awaiting_input counts", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.advance(sid);
    backend.advance(sid);
    expect(status(backend, sid).status).toBe("awaiting_input");
    expect(backend.cancelSession(U, sid)).toEqual({ counted: true });
  });

  it("running reports the run's counted and adds no new charge", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.settle(sid);
    backend.confirmSpeaker(U, sid, "spk_0");
    backend.putRating(U, sid, { final: true, card: SCORED });
    expect(status(backend, sid).status).toBe("running");
    const before = usedEval(backend);
    expect(backend.cancelSession(U, sid)).toEqual({ counted: true });
    expect(usedEval(backend)).toBe(before);
    expect(backend.listRuns(U, sid).at(-1)?.status).toBe("failed");
  });

  it("an interview-linked session is never counted", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.advance(sid);
    backend.advance(sid);
    (backend as unknown as { sessions: Map<string, { interview_id?: string }> }).sessions.get(sid)!.interview_id = "iv_1";
    expect(backend.cancelSession(U, sid)).toEqual({ counted: false });
  });

  it("repeating returns the same counted and charges nothing more", () => {
    const { backend } = ctx;
    const sid = started(backend);
    backend.advance(sid);
    backend.advance(sid);
    expect(backend.cancelSession(U, sid)).toEqual({ counted: true });
    expect(backend.cancelSession(U, sid)).toEqual({ counted: true });
    expect(usedEval(backend)).toBe(1);
  });

  it("is 409 for report_ready and failed, 404 for another user's session", () => {
    const { backend } = ctx;
    const failed = started(backend, "fail-no_speech");
    backend.settle(failed);
    expectHttp(() => backend.cancelSession(U, failed), 409, "invalid_state");
    const ok = started(backend);
    backend.settle(ok);
    backend.confirmSpeaker(U, ok, "spk_0");
    backend.putRating(U, ok, { final: true, card: SCORED });
    backend.settle(ok);
    expect(status(backend, ok).status).toBe("report_ready");
    expectHttp(() => backend.cancelSession(U, ok), 409, "invalid_state");
    expectHttp(() => backend.cancelSession("other", ok), 404, "not_found");
  });

  it("is allowed over the cap and the worker no longer moves a cancelled session", () => {
    const { backend } = make({ caps: { eval: { day: 0 } } });
    const sid = started(backend);
    backend.advance(sid);
    backend.advance(sid);
    expect(backend.cancelSession(U, sid)).toEqual({ counted: true });
    expect(backend.advance(sid)).toBe(false);
  });
});

describe("cancelled sessions answer 409 invalid_state (04-cancel R6)", () => {
  it("rating, speakers, runs, retry, upload and transcript routes", () => {
    const { backend: b } = make();
    const uid = "u1";
    const sid = b.createSession(uid, {}).session.id;
    b.cancelSession(uid, sid);
    const code = (fn: () => unknown) => {
      try {
        fn();
      } catch (e) {
        return (e as { status?: number }).status;
      }
      return "no error";
    };
    expect(code(() => b.putRating(uid, sid, { card: {} } as never))).toBe(409);
    expect(code(() => b.confirmSpeaker(uid, sid, "A"))).toBe(409);
    expect(code(() => b.startRun(uid, sid, {}))).toBe(409);
    expect(code(() => b.retrySession(uid, sid))).toBe(409);
    expect(code(() => b.requestAudio(uid, sid, { content_type: "audio/mpeg", size_bytes: 1, filename_ext: "mp3" }))).toBe(409);
    expect(code(() => b.completeAudio(uid, sid))).toBe(409);
  });
});
