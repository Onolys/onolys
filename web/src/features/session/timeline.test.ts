import { afterEach, describe, expect, it, vi } from "vitest";
import { deriveTimeline, STEP_LABELS, type TimelineInput } from "./timeline";

type SessionState = TimelineInput["state"];

const STATES: SessionState[] = [
  "created",
  "uploading",
  "upload_incomplete",
  "upload_failed",
  "validating",
  "transcribing",
  "awaiting_input",
  "running",
  "report_ready",
  "failed",
  "cancelled",
  "deleting",
];

interface Flags {
  transcript_ready: boolean;
  speaker_confirmed: boolean;
  rating_submitted: boolean;
}
const none: Flags = { transcript_ready: false, speaker_confirmed: false, rating_submitted: false };
const T = { transcript_ready: true };
const S = { speaker_confirmed: true };
const R = { rating_submitted: true };

// Steps (rating on): upload, transcribe, speaker, rating, run, report.
// d = done, c = current, p = pending, f = failed.
type Row = [
  name: string,
  state: SessionState,
  flags: Partial<Flags>,
  extra: { step?: string | null; error_code?: string | null },
  statuses: string,
  lines: string[],
];

const ROWS: Row[] = [
  ["created", "created", {}, {}, "cppppp", ["Getting ready to upload your recording."]],
  ["created, rating already filled", "created", R, {}, "cppdpp", ["Getting ready to upload your recording."]],
  ["uploading", "uploading", {}, {}, "cppppp", ["Uploading your recording."]],
  ["validating", "validating", {}, {}, "dcpppp", ["Checking your audio."]],
  ["validating, rating filled early", "validating", R, {}, "dcpdpp", ["Checking your audio."]],
  ["transcribing", "transcribing", {}, {}, "dcpppp", ["Transcribing the recording."]],
  ["transcribing, rating filled early", "transcribing", R, {}, "dcpdpp", ["Transcribing the recording."]],
  [
    "awaiting_input: speaker and rating missing",
    "awaiting_input",
    T,
    {},
    "ddccpp",
    ["Confirm who the clinician is", "Waiting for your rating"],
  ],
  ["awaiting_input: speaker missing", "awaiting_input", { ...T, ...R }, {}, "ddcdpp", ["Confirm who the clinician is"]],
  ["awaiting_input: rating missing", "awaiting_input", { ...T, ...S }, {}, "dddcpp", ["Waiting for your rating"]],
  ["awaiting_input: all in, starting", "awaiting_input", { ...T, ...S, ...R }, {}, "ddddpp", ["Starting the rating."]],
  [
    "awaiting_input: cap reached",
    "awaiting_input",
    { ...T, ...S, ...R },
    { error_code: "daily_cap_reached" },
    "ddddpp",
    ["You've reached today's limit. You can start the rating after 9:00 AM."],
  ],
  ["running, code", "running", { ...T, ...S, ...R }, { step: "code" }, "ddddcp", ["Coding the session"]],
  ["running, tips", "running", { ...T, ...S, ...R }, { step: "tips" }, "ddddcp", ["Writing tips"]],
  ["running, assemble", "running", { ...T, ...S, ...R }, { step: "assemble" }, "ddddcp", ["Building the report"]],
  ["running, no step yet", "running", { ...T, ...S, ...R }, { step: null }, "ddddcp", ["Coding the session"]],
  ["running, unknown step", "running", { ...T, ...S, ...R }, { step: "zzz" }, "ddddcp", ["Coding the session"]],
  ["running, legacy step name", "running", { ...T, ...S, ...R }, { step: "paudit" }, "ddddcp", ["Coding the session"]],
  ["report_ready", "report_ready", { ...T, ...S, ...R }, {}, "dddddd", ["Your report is ready."]],
  [
    "failed, file-check code, pre-transcript",
    "failed",
    {},
    { error_code: "audio_unreadable" },
    "dfpppp",
    ["This session couldn't be completed."],
  ],
  [
    "failed at transcribe",
    "failed",
    {},
    { error_code: "no_speech" },
    "dfpppp",
    ["This session couldn't be completed."],
  ],
  [
    "failed at transcribe (speakers_not_separated)",
    "failed",
    {},
    { error_code: "speakers_not_separated" },
    "dfpppp",
    ["This session couldn't be completed."],
  ],
  [
    "failed during run",
    "failed",
    { ...T, ...S, ...R },
    { error_code: "internal_error", step: null },
    "ddddfp",
    ["This session couldn't be completed."],
  ],
  [
    "failed during run, rating missing",
    "failed",
    { ...T, ...S },
    { error_code: "upstream_unavailable" },
    "dddpfp",
    ["This session couldn't be completed."],
  ],
  ["deleting", "deleting", { ...T, ...S, ...R }, {}, "pppppp", ["Deleting this session."]],
  ["upload_incomplete", "upload_incomplete", {}, {}, "cppppp", ["Your upload didn't finish. Pick the file again to resume, or delete this session."]],
  ["cancelled", "cancelled", { ...T, ...S, ...R }, {}, "pppppp", ["This session was cancelled."]],
  ["upload_failed", "upload_failed", {}, {}, "pppppp", ["This session couldn't be completed."]],
];

const ON_KEYS = ["upload", "transcribe", "speaker", "rating", "run", "report"];
const ON_LABELS = ["Upload", "Transcribe", "Confirm speaker", "Your rating", "Rate session", "Report"];
const OFF_KEYS = ON_KEYS.filter((k) => k !== "rating");
const OFF_LABELS = ON_LABELS.filter((l) => l !== "Your rating");
const dropRating = (statuses: string) => statuses.slice(0, 3) + statuses.slice(4);
const doc = (state: SessionState, flags: Partial<Flags>, extra: { step?: string | null; error_code?: string | null }) => ({
  state,
  step: extra.step ?? null,
  error_code: extra.error_code ?? null,
  ...none,
  ...flags,
});

describe("deriveTimeline: table (rating flag on)", () => {
  it.each(ROWS)("%s", (_name, state, flags, extra, statuses, lines) => {
    const t = deriveTimeline(doc(state, flags, extra), { resetsAt: "9:00 AM", ratingEnabled: true });
    expect(t.steps.map((s) => s.key)).toEqual(ON_KEYS);
    expect(t.steps.map((s) => s.label)).toEqual(ON_LABELS);
    expect(t.steps.map((s) => s.status[0]).join("")).toBe(statuses);
    expect(t.lines).toEqual(lines);
  });

  it("keeps the label list in step order", () => {
    expect(STEP_LABELS).toEqual(["Upload", "Transcribe", "Confirm speaker", "Your rating", "Rate session", "Report"]);
  });
});

describe("deriveTimeline: table (rating flag off)", () => {
  afterEach(() => vi.unstubAllEnvs());

  it.each(ROWS)("%s", (_name, state, flags, extra, statuses, lines) => {
    const t = deriveTimeline(doc(state, flags, extra), { resetsAt: "9:00 AM", ratingEnabled: false });
    expect(t.steps.map((s) => s.key)).toEqual(OFF_KEYS);
    expect(t.steps.map((s) => s.label)).toEqual(OFF_LABELS);
    expect(t.steps.map((s) => s.status[0]).join("")).toBe(dropRating(statuses));
    expect(t.lines).toEqual(lines.map((l) => (l === "Waiting for your rating" ? "Waiting for your change goal" : l)));
  });

  it("awaiting input with the goal missing reads 'Waiting for your change goal'", () => {
    const t = deriveTimeline(doc("awaiting_input", { ...T, ...S }, {}), { ratingEnabled: false });
    expect(t.lines).toEqual(["Waiting for your change goal"]);
  });

  it("defaults to the env flag: off when absent, on when VITE_RATING_ENABLED=true", () => {
    const d = doc("awaiting_input", { ...T, ...S }, {});
    vi.stubEnv("VITE_RATING_ENABLED", "");
    expect(deriveTimeline(d).lines).toEqual(["Waiting for your change goal"]);
    expect(deriveTimeline(d).steps.map((s) => s.key)).toEqual(OFF_KEYS);
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    expect(deriveTimeline(d).lines).toEqual(["Waiting for your rating"]);
    expect(deriveTimeline(d).steps.map((s) => s.key)).toEqual(ON_KEYS);
  });
});

describe("deriveTimeline: sub-labels", () => {
  it.each([
    ["validating", "transcribe", "Checking audio"],
    ["transcribing", "transcribe", undefined],
    ["running", "run", "Coding the session"],
    ["awaiting_input", "transcribe", undefined],
    ["failed", "transcribe", undefined],
  ] as const)("%s puts %j sub-label on %s only", (state, key, sub) => {
    const t = deriveTimeline(doc(state, { ...T }, {}), { ratingEnabled: false });
    expect(t.steps.find((s) => s.key === key)?.subLabel).toBe(sub);
    expect(t.steps.filter((s) => s.subLabel)).toHaveLength(sub ? 1 : 0);
  });
});

describe("deriveTimeline: hint (PRD R5)", () => {
  const UPLOAD = "Keep this tab open until upload finishes";
  const BACKGROUND = "You can close this tab \u2014 we'll keep working";
  const WAITING = "We'll wait here for your choice";
  const HINTS: [SessionState, string | null][] = [
    ["created", UPLOAD],
    ["uploading", UPLOAD],
    ["upload_incomplete", UPLOAD],
    ["validating", BACKGROUND],
    ["transcribing", BACKGROUND],
    ["running", BACKGROUND],
    ["awaiting_input", WAITING],
    ["report_ready", null],
    ["failed", null],
    ["cancelled", null],
    ["upload_failed", null],
    ["deleting", null],
  ];
  it.each(HINTS)("%s -> %j", (state, hint) => {
    expect(deriveTimeline(doc(state, { ...T, ...S, ...R }, {})).hint).toBe(hint);
  });
  it("covers every state", () => {
    expect(HINTS.map(([s]) => s).sort()).toEqual([...STATES].sort());
  });
});

describe("deriveTimeline: every state x flag combination", () => {
  const bools = [false, true];
  const combos = STATES.flatMap((state) =>
    bools.flatMap((t) =>
      bools.flatMap((s) =>
        bools.map((r) => ({ state, transcript_ready: t, speaker_confirmed: s, rating_submitted: r })),
      ),
    ),
  );

  it.each(combos)("%o has coherent steps and copy", (c) => {
    for (const ratingOn of bools) {
      const t = deriveTimeline({ ...c, step: null, error_code: null }, { ratingEnabled: ratingOn });
      expect(t.steps).toHaveLength(ratingOn ? 6 : 5);
      expect(t.lines.length).toBeGreaterThan(0);
      expect(t.lines.every((l) => l.trim().length > 0)).toBe(true);
      const byKey = Object.fromEntries(t.steps.map((s) => [s.key, s.status]));
      const terminalPending = ["deleting", "cancelled", "upload_failed"].includes(c.state);
      if (!terminalPending) {
        if (c.speaker_confirmed) expect(byKey.speaker).toBe("done");
        if (ratingOn && c.rating_submitted) expect(byKey.rating).toBe("done");
      } else {
        expect(t.steps.every((s) => s.status === "pending")).toBe(true);
      }
      if (c.state === "report_ready") expect(byKey.report).toBe("done");
      if (c.state !== "report_ready") expect(byKey.report).toBe("pending");
      expect(t.steps.filter((s) => s.status === "failed")).toHaveLength(c.state === "failed" ? 1 : 0);
      const copy = t.lines.join(" ");
      if (c.state === "awaiting_input") {
        expect(copy.includes("Confirm who the clinician is")).toBe(!c.speaker_confirmed);
        const wait = ratingOn ? "Waiting for your rating" : "Waiting for your change goal";
        expect(copy.includes(wait)).toBe(!c.rating_submitted);
      }
      expect(copy).not.toMatch(/Check audio|Session setup|under 5 minutes/);
    }
  });
});

describe("deriveTimeline: extras", () => {
  const base = { state: "running" as const, step: "tips", error_code: null, ...none, ...T, ...S, ...R };

  it("puts the sub-label from step on the running step only", () => {
    const t = deriveTimeline(base);
    expect(t.steps.find((s) => s.key === "run")?.subLabel).toBe("Writing tips");
    expect(t.steps.filter((s) => s.subLabel)).toHaveLength(1);
  });

  it("shows the 'close this tab' copy once the run has started and not before", () => {
    expect(deriveTimeline(base).showRunCopy).toBe(true);
    expect(deriveTimeline({ ...base, state: "transcribing" }).showRunCopy).toBe(false);
    expect(deriveTimeline({ ...base, state: "report_ready" }).showRunCopy).toBe(false);
  });

  it("flags the cap message with a Start action", () => {
    const t = deriveTimeline({ ...base, state: "awaiting_input", error_code: "daily_cap_reached" });
    expect(t.capReached).toBe(true);
    expect(t.lines[0]).toBe("You've reached today's limit.");
  });

  it("a start held by an active run offers Start with the concurrent message, not the reset time", () => {
    const t = deriveTimeline(
      { ...base, state: "awaiting_input", error_code: "concurrent_runs" },
      { resetsAt: "3:00 PM" },
    );
    expect(t.capReached).toBe(true);
    expect(t.lines).toEqual(["You already have a rating running. Wait for it to finish."]);
    expect(t.lines.join(" ")).not.toMatch(/limit|3:00/i);
  });

  it("does not offer Start for a cap code outside awaiting_input", () => {
    expect(deriveTimeline({ ...base, state: "failed", error_code: "daily_cap_reached" }).capReached).toBe(false);
  });
});
