/**
 * In-memory mock of the SP04 API (PRD R4/R7, D5). Pure TypeScript, no MSW and
 * no timers: HTTP handlers call it, tests drive it with `advance`/`settle`, and
 * the browser worker advances it on an interval. Every state change is mirrored
 * to a PHI-free `session_status` doc through the status emitter.
 */
import type { Report } from "../api/report";
import type { components } from "../api/schema";
import type { ErrorCode, RatingCard, SessionState } from "../api/types";

type RunStage = "paudit" | "eaudit" | "tips" | "compare" | "assemble";
import type { MemoryStatusEmitter, SessionStatusDoc } from "../api/statusListener";
import {
  edgeTranscript,
  reportFor,
  sampleLines,
  sampleTranscript,
  threeSpeakerTranscript,
  type Turn,
} from "./fixtures";

import { MOCK_CHANGE_GOALS, MOCK_LIMITS, MOCK_SCENARIOS, MOCK_VOICES } from "./fixtures/scenarios";

type S = components["schemas"];

export class MockHttpError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: S["ErrorDetailModel"][];
  constructor(status: number, code: string, message: string, details?: S["ErrorDetailModel"][]) {
    super(message);
    this.name = "MockHttpError";
    this.status = status;
    this.code = code;
    this.details = details ?? [{ code: code as ErrorCode, message }];
  }
}

export type CapKind = "eval" | "interview";
export type CapPeriod = "day";
export type Caps = Record<CapKind, Record<CapPeriod, number>>;
export type CapsOverride = { [K in CapKind]?: Partial<Record<CapPeriod, number>> };

const DEFAULT_CAPS: Caps = { eval: { day: 20 }, interview: { day: 5 } };
const CAP_CODE: Record<CapKind, (p: CapPeriod) => ErrorCode> = {
  eval: () => "daily_cap_reached",
  interview: () => "interview_cap_reached",
};

function mergeCaps(base: Caps, o: CapsOverride = {}): Caps {
  return {
    eval: { ...base.eval, ...o.eval },
    interview: { ...base.interview, ...o.interview },
  };
}

export interface MockOptions {
  emitter: MemoryStatusEmitter;
  /** Per-kind daily caps; unset values use the defaults. */
  caps?: CapsOverride;
  now?: () => Date;
}

const MAX_AUDIO_BYTES = 300 * 1024 * 1024;
const PRESETS = ["default", "fast"];
const STAGES: RunStage[] = ["paudit", "eaudit", "tips", "compare", "assemble"];
/** SP04 R4 progress table: weights added as each stage finishes. */
const STAGE_WEIGHT: Record<RunStage, number> = { paudit: 25, eaudit: 15, tips: 8, compare: 4, assemble: 3 };
const RUN_START_PROGRESS = 45;

const CANONICAL: Record<string, { ext: string; types: string[]; canonical: string }> = {
  mp3: { ext: "mp3", types: ["audio/mpeg", "audio/mp3"], canonical: "audio/mpeg" },
  wav: { ext: "wav", types: ["audio/wav", "audio/x-wav", "audio/wave"], canonical: "audio/wav" },
  m4a: { ext: "m4a", types: ["audio/mp4", "audio/x-m4a", "audio/m4a"], canonical: "audio/mp4" },
  webm: { ext: "webm", types: ["audio/webm"], canonical: "audio/webm" },
  ogg: { ext: "ogg", types: ["audio/ogg", "application/ogg"], canonical: "audio/ogg" },
};

/** Failure injection by magic session title (like the SP04 fake adapters). */
const VALIDATE_FAILS = ["audio_unreadable", "unsupported_audio", "audio_too_long", "audio_too_large"];
const TRANSCRIBE_FAILS = ["no_speech", "speakers_not_separated", "transcription_failed"];

interface Rating {
  rating_id: string;
  no_rating: boolean;
  has_content: boolean;
  card: RatingCard;
  seq: number;
}

type RunRec = S["RunView"] & { stageIdx: number };

interface ReportRec {
  version: number;
  report_id: string;
  run_id: string;
  created_at: string;
  report: Report;
}

interface SessionRec {
  id: string;
  uid: string;
  seq: number;
  title: string | null;
  language: string;
  n_runs: number;
  preset: string;
  created_at: string;
  updated_at: string;
  state: SessionState;
  step: string | null;
  progress: number;
  error: { code: string; step?: string } | null;
  flags: S["Flags"];
  clinician_speaker: string | null;
  first_run_id: string | null;
  holdFirstStart: boolean;
  uploadId: string | null;
  uploadType: string | null;
  interview_id?: string;
  finals: Rating[];
  draft: { card: RatingCard; updated_at: string; seq: number } | null;
  runs: RunRec[];
  reports: ReportRec[];
}

/** Failures a retry cannot fix: the file itself is the problem (mirrors the API's BAD_FILE_CODES). */
const BAD_FILE_CODES = new Set([
  "unsupported_audio",
  "audio_too_long",
  "interview_too_long",
  "audio_too_large",
  "audio_unreadable",
  "no_speech",
  "speakers_not_separated",
  "transcription_failed",
]);

function bad(status: number, code: string, message: string, details?: S["ErrorDetailModel"][]): never {
  throw new MockHttpError(status, code, message, details);
}

function notFound(): never {
  return bad(404, "not_found", "Not found.");
}

function invalidParam(message: string): never {
  return bad(422, "invalid_parameters", message);
}

export class MockBackend {
  private readonly emitter: MemoryStatusEmitter;
  private readonly now: () => Date;
  private readonly initialCaps: Caps;
  private caps: Caps;
  private sessions = new Map<string, SessionRec>();
  /** Successful uses, keyed `kind:uid:day` and `kind:uid:month`. */
  private counters = new Map<string, number>();
  private idem = new Map<string, { hash: string; response: S["CreateSessionResponse"] }>();
  private apiKeys = new Map<string, { key_id: string; created: string }>();
  private interviews = new Map<string, { uid: string; res: S["InterviewResponse"]; session_id?: string }>();
  private n = 0;

  constructor(opts: MockOptions) {
    this.emitter = opts.emitter;
    this.now = opts.now ?? (() => new Date());
    this.initialCaps = this.caps = mergeCaps(DEFAULT_CAPS, opts.caps);
  }

  /** Drop all data and restore options (used between tests). */
  reset(): void {
    this.sessions.clear();
    this.counters.clear();
    this.idem.clear();
    this.apiKeys.clear();
    this.interviews.clear();
    this.n = 0;
    this.caps = this.initialCaps;
    this.emitter.clear();
  }

  configure(o: { caps?: CapsOverride }): void {
    this.caps = mergeCaps(this.caps, o.caps);
  }

  // ---- helpers ------------------------------------------------------------

  private id(prefix: string): string {
    this.n += 1;
    return `${prefix}_${this.n}`;
  }

  private own(uid: string, sid: string): SessionRec {
    const s = this.sessions.get(sid);
    if (!s || s.uid !== uid) notFound();
    return s as SessionRec;
  }

  private emit(s: SessionRec): void {
    s.updated_at = this.now().toISOString();
    const doc: SessionStatusDoc = {
      uid: s.uid,
      state: s.state,
      step: s.step,
      progress: s.progress,
      error_code: s.error?.code ?? null,
      latest_report_version: s.reports.at(-1)?.version ?? null,
      updated_at: this.now().toISOString(),
      ...s.flags,
    };
    this.emitter.emit(s.id, doc);
  }

  private counterKey(uid: string, kind: CapKind, period: CapPeriod): string {
    const iso = this.now().toISOString();
    return `${kind}:${uid}:${period}:${iso.slice(0, 10)}`;
  }

  private used(uid: string, kind: CapKind, period: CapPeriod): number {
    return this.counters.get(this.counterKey(uid, kind, period)) ?? 0;
  }

  private resetsAt(): string {
    const d = this.now();
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1)).toISOString();
  }

  /** The exhausted period for a kind, or null. */
  private blocked(uid: string, kind: CapKind): CapPeriod | null {
    for (const p of ["day"] as const) if (this.used(uid, kind, p) >= this.caps[kind][p]) return p;
    return null;
  }

  /** The 429 for an exhausted kind (code per kind and period, `period` in the detail), else nothing. */
  checkCap(uid: string, kind: CapKind): void {
    const period = this.blocked(uid, kind);
    if (!period) return;
    const code = CAP_CODE[kind](period);
    bad(429, code, `${kind} ${period} limit reached.`, [{ code, message: `${kind} ${period} limit reached.`, period }]);
  }

  /** Count one use of a kind. Callers check the cap first. */
  private count(uid: string, kind: CapKind): void {
    for (const p of ["day"] as const) {
      const key = this.counterKey(uid, kind, p);
      this.counters.set(key, (this.counters.get(key) ?? 0) + 1);
    }
  }

  /** Start an interview against its caps (429 `interview_cap_reached` when exhausted). For SP10. */
  consumeInterview(uid: string): void {
    this.checkCap(uid, "interview");
    this.count(uid, "interview");
  }

  // ---- SP10 AI interviews --------------------------------------------------

  listScenarios(): S["ScenarioList"] {
    return { scenarios: MOCK_SCENARIOS.map((s) => ({ ...s })), voices: [...MOCK_VOICES] };
  }

  /** Start an interview: validate, spend a cap slot (429 `interview_cap_reached`), return the relay URL. */
  createInterview(uid: string, body: S["CreateInterviewRequest"]): S["InterviewResponse"] {
    const scenario = MOCK_SCENARIOS.find((s) => s.id === body?.scenario_id);
    if (!scenario) invalidParam("scenario_id is not a known scenario");
    if (body.voice != null && !MOCK_VOICES.includes(body.voice)) invalidParam("voice is not allowed");
    this.consumeInterview(uid);
    this.n += 1;
    const interview_id = `iv_mock${this.n}`;
    const res: S["InterviewResponse"] = {
      interview_id,
      state: "created",
      scenario: { ...scenario },
      voice: body.voice ?? scenario.voice,
      voice_url: `wss://relay.mock.invalid/v1/voice/${interview_id}`,
      limits: { ...MOCK_LIMITS },
    };
    this.interviews.set(interview_id, { uid, res });
    return { ...res };
  }

  getInterview(uid: string, id: string): S["InterviewResponse"] {
    const rec = this.interviews.get(id);
    if (!rec || rec.uid !== uid) notFound();
    return { ...rec.res };
  }

  /** Mock stand-in for the relay: `live` on connect, `duration_s` as recorded. */
  setInterviewState(id: string, state: S["InterviewResponse"]["state"], duration_s?: number): void {
    const rec = this.interviews.get(id);
    if (!rec) notFound();
    rec.res = { ...rec.res, state, ...(duration_s !== undefined ? { duration_s } : {}) };
  }

  endInterview(uid: string, id: string, body?: S["EndInterviewRequest"] | null): S["InterviewResponse"] {
    const rec = this.interviews.get(id);
    if (!rec || rec.uid !== uid) notFound();
    if (rec.res.state === "ended" || rec.res.state === "abandoned" || rec.res.state === "uploaded") return { ...rec.res };
    rec.res = { ...rec.res, state: body?.discard ? "abandoned" : "ended" };
    return { ...rec.res };
  }

  private titleIs(s: SessionRec, name: string): boolean {
    return (s.title ?? "").trim().toLowerCase() === name;
  }

  private injected(s: SessionRec, codes: string[]): string | undefined {
    return codes.find((c) => this.titleIs(s, `fail-${c}`));
  }

  private turns(s: SessionRec): Turn[] {
    if (this.titleIs(s, "utf8-edge")) return edgeTranscript;
    if (this.titleIs(s, "three-speakers")) return threeSpeakerTranscript;
    return sampleTranscript;
  }

  private fail(s: SessionRec, code: string, step: string): void {
    s.state = "failed";
    s.error = { code, step };
    s.step = null;
    this.emit(s);
  }

  // ---- sessions -----------------------------------------------------------

  createSession(
    uid: string,
    body: S["CreateSessionRequest"],
    idempotencyKey?: string,
  ): S["CreateSessionResponse"] {
    if (body.language !== undefined && body.language !== "auto" && !/^[a-z]{2,3}(-[A-Z]{2})?$/.test(body.language))
      invalidParam("language is not a valid BCP-47 tag or auto");
    if (body.n_runs != null && (!Number.isInteger(body.n_runs) || body.n_runs < 1 || body.n_runs > 5))
      invalidParam("n_runs must be an integer from 1 to 5");
    if (body.preset != null && !PRESETS.includes(body.preset)) invalidParam("preset is not allowed");
    if (body.title != null && (typeof body.title !== "string" || body.title.length > 200))
      invalidParam("title is too long");

    // SP10 link: an ended, unlinked interview of the caller; language and the draft change goal come from its scenario.
    const linked = body.interview_id ? this.interviews.get(body.interview_id) : undefined;
    if (body.interview_id) {
      if (!linked || linked.uid !== uid) notFound();
    }

    const idemKey = idempotencyKey ? `${uid}:${idempotencyKey}` : null;
    const hash = JSON.stringify(body);
    if (idemKey) {
      const prior = this.idem.get(idemKey);
      if (prior) {
        if (prior.hash !== hash) bad(409, "conflict", "Idempotency-Key reused with a different body.");
        return prior.response;
      }
    }

    if (linked) {
      if (linked.session_id) bad(409, "conflict", "Interview already linked to a session.");
      if (linked.res.state !== "ended") bad(409, "invalid_state", "Interview is not ended.");
    }

    const seq = this.n + 1;
    const id = this.id("s");
    const s: SessionRec = {
      id,
      uid,
      seq,
      title: body.title ?? linked?.res.scenario.title ?? null,
      language: linked ? linked.res.scenario.language : (body.language ?? "auto"),
      n_runs: body.n_runs ?? 1,
      preset: body.preset ?? "default",
      created_at: this.now().toISOString(),
      updated_at: this.now().toISOString(),
      state: "created",
      step: null,
      progress: 0,
      error: null,
      flags: { transcript_ready: false, speaker_confirmed: false, rating_submitted: false, has_rating: false },
      clinician_speaker: null,
      first_run_id: null,
      holdFirstStart: false,
      uploadId: null,
      uploadType: null,
      finals: [],
      draft: null,
      runs: [],
      reports: [],
    };
    s.holdFirstStart = this.titleIs(s, "cap-held");
    if (linked && body.interview_id) {
      s.interview_id = body.interview_id;
      linked.session_id = id;
      const goal = MOCK_CHANGE_GOALS[linked.res.scenario.id];
      if (goal) s.draft = { card: { change_goal: goal } as RatingCard, updated_at: s.created_at, seq: seq };
    }
    this.sessions.set(id, s);
    this.emit(s); // before returning, so a listener can attach at once
    const response = { session: { id, status: s.state } };
    if (idemKey) this.idem.set(idemKey, { hash, response });
    return response;
  }

  listSessions(uid: string, q: { limit?: number; cursor?: string }): S["SessionList"] {
    const limit = Math.min(Math.max(q.limit ?? 20, 1), 50);
    const offset = q.cursor ? Number.parseInt(q.cursor, 10) || 0 : 0;
    const all = [...this.sessions.values()].filter((s) => s.uid === uid).sort((a, b) => b.seq - a.seq);
    const items = all.slice(offset, offset + limit).map((s) => ({
      id: s.id,
      title: s.title,
      status: s.state,
      created_at: s.created_at,
      latest_report_version: s.reports.at(-1)?.version ?? null,
      error_code: s.error?.code ?? null,
      interview_id: s.interview_id ?? null,
    }));
    const next = offset + limit;
    return next < all.length ? { items, next_cursor: String(next) } : { items };
  }

  getSession(uid: string, sid: string): S["SessionDetail"] {
    const s = this.own(uid, sid);
    const detail: S["SessionDetail"] = {
      id: s.id,
      title: s.title,
      status: s.state,
      step: s.step,
      progress: s.progress,
      flags: { ...s.flags },
      warnings: [],
      latest_report_version: s.reports.at(-1)?.version ?? null,
      created_at: s.created_at,
      updated_at: s.updated_at,
      language: s.language,
      n_runs: s.n_runs,
      preset: s.preset,
      interview_id: s.interview_id ?? null,
      links: { self: `/v1/sessions/${s.id}` },
    };
    if (s.error) detail.error = { ...s.error };
    return detail;
  }

  deleteSession(uid: string, sid: string): void {
    const s = this.own(uid, sid);
    s.state = "deleting";
    this.emit(s);
    this.sessions.delete(sid);
    this.emitter.remove(sid);
  }

  // ---- audio --------------------------------------------------------------

  requestAudio(uid: string, sid: string, body: S["AudioUploadRequest"]): S["AudioUploadResponse"] {
    const s = this.own(uid, sid);
    if (s.state !== "created" && s.state !== "uploading" && s.state !== "upload_incomplete")
      bad(409, "invalid_state", "Audio can no longer be uploaded.");
    const ext = (body.filename_ext ?? "").replace(/^\./, "").toLowerCase();
    const type = (body.content_type ?? "").toLowerCase();
    const byType = Object.values(CANONICAL).find((f) => f.types.includes(type));
    const byExt = CANONICAL[ext];
    const format = type === "" ? byExt : byType;
    if (!format) bad(422, "unsupported_audio", "Unsupported audio type.");
    if (!(body.size_bytes >= 0) || body.size_bytes > MAX_AUDIO_BYTES)
      bad(422, "audio_too_large", "Audio file is too large.");

    s.uploadId = this.id("up");
    s.uploadType = format.canonical;
    s.state = "uploading";
    s.step = null;
    s.progress = 5;
    this.emit(s);
    return {
      upload_url: `https://uploads.mock.invalid/uploads/${uid}/${sid}/${s.uploadId}`,
      upload_id: s.uploadId,
      required_headers: {
        "Content-Type": format.canonical,
        "x-goog-content-length-range": `0,${MAX_AUDIO_BYTES}`,
      },
    };
  }

  /** The canonical Content-Type a signed URL is pinned to (for the PUT handler). */
  uploadContentType(sid: string, uploadId: string): string | undefined {
    const s = this.sessions.get(sid);
    return s && s.uploadId === uploadId ? (s.uploadType ?? undefined) : undefined;
  }

  completeAudio(uid: string, sid: string): S["CreateSessionResponse"] {
    const s = this.own(uid, sid);
    if (s.state !== "uploading" && s.state !== "upload_incomplete")
      bad(409, "invalid_state", "No upload is in progress.");
    s.state = "validating";
    s.step = "validate";
    s.progress = 10;
    this.emit(s);
    return { session: { id: s.id, status: s.state } };
  }

  // ---- rating -------------------------------------------------------------

  putRating(uid: string, sid: string, body: S["RatingRequest"]): S["RatingSaved"] {
    const s = this.own(uid, sid);
    if (s.state === "deleting") bad(409, "invalid_state", "Session is being deleted.");
    const card = (body.card ?? {}) as RatingCard;
    validateCard(card, body.final === true);
    if (body.final === true && (s.flags.rating_submitted || s.state === "report_ready" || s.reports.length > 0)) {
      bad(409, "rating_final", "The rating is final once submitted.");
    }
    const seq = this.n + 1;
    this.n += 1;
    if (!body.final) {
      const updated_at = this.now().toISOString();
      s.draft = { card, updated_at, seq };
      return { final: false, updated_at };
    }
    const noRating = body.no_rating === true;
    const stored: RatingCard = noRating
      ? { change_goal: card.change_goal, coded_span: card.coded_span ?? null }
      : card;
    const rating: Rating = {
      rating_id: this.id("rt"),
      no_rating: noRating,
      has_content: !noRating && cardHasContent(card),
      card: stored,
      seq,
    };
    s.finals.push(rating);
    s.flags.rating_submitted = true;
    s.flags.has_rating = rating.has_content;
    this.emit(s);
    this.maybeStartFirstRun(s);
    return {
      final: true,
      rating_id: rating.rating_id,
      no_rating: rating.no_rating,
      has_rating: rating.has_content,
      updated_at: this.now().toISOString(),
    };
  }

  getRating(uid: string, sid: string): S["RatingView"] {
    const s = this.own(uid, sid);
    const final = s.finals.at(-1);
    const out: S["RatingView"] = {};
    if (final) out.final = { rating_id: final.rating_id, no_rating: final.no_rating, card: final.card };
    if (s.draft && (!final || s.draft.seq > final.seq))
      out.draft = { card: s.draft.card, updated_at: s.draft.updated_at };
    return out;
  }

  // ---- speakers, transcript ----------------------------------------------

  getSpeakers(uid: string, sid: string): S["SpeakersView"] {
    const s = this.own(uid, sid);
    if (!s.flags.transcript_ready) bad(409, "invalid_state", "Transcript is not ready.");
    return { speakers: sampleLines(this.turns(s)), clinician_speaker: s.clinician_speaker };
  }

  confirmSpeaker(uid: string, sid: string, speaker: string): S["CreateSessionResponse"] {
    const s = this.own(uid, sid);
    if (!s.flags.transcript_ready || s.state === "running" || s.state === "deleting")
      bad(409, "invalid_state", "Speakers cannot be confirmed now.");
    if (!this.turns(s).some((t) => t.speaker === speaker)) invalidParam("clinician_speaker is not a speaker");
    s.clinician_speaker = speaker;
    s.flags.speaker_confirmed = true;
    this.emit(s);
    if (s.state === "awaiting_input") this.maybeStartFirstRun(s);
    return { session: { id: s.id, status: s.state } };
  }

  getTranscript(uid: string, sid: string): S["TranscriptView"] {
    const s = this.own(uid, sid);
    if (!s.flags.transcript_ready) bad(409, "invalid_state", "Transcript is not ready.");
    const turns = this.turns(s).map((t) => ({
      ...t,
      role:
        s.clinician_speaker === null
          ? null
          : t.speaker === s.clinician_speaker
            ? ("clinician" as const)
            : ("client" as const),
    }));
    return {
      turns,
      language: s.language === "auto" ? "en-US" : s.language,
      duration_ms: turns.at(-1)?.end_ms ?? 0,
      clinician_speaker: s.clinician_speaker,
    };
  }

  // ---- runs, reports, usage ----------------------------------------------

  /** Start the first run once transcript + speaker + final rating are in (SP04 R4). */
  private maybeStartFirstRun(s: SessionRec): void {
    const f = s.flags;
    if (s.state !== "awaiting_input" || s.first_run_id) return;
    if (!(f.transcript_ready && f.speaker_confirmed && f.rating_submitted)) return;
    const blocked = this.blocked(s.uid, "eval");
    if (s.holdFirstStart || blocked) {
      s.error = { code: blocked ? CAP_CODE.eval(blocked) : "daily_cap_reached" };
      this.emit(s);
      return;
    }
    this.createRun(s, {});
  }

  private createRun(s: SessionRec, p: S["RunRequest"]): RunRec {
    const run: RunRec = {
      run_id: this.id("r"),
      session_id: s.id,
      attempts: 1,
      started: this.now().toISOString(),
      status: "running",
      n_runs: p.n_runs ?? s.n_runs,
      preset: p.preset ?? s.preset,
      stt: { provider: "mock", model: "mock-stt", language: s.language === "auto" ? "en-US" : s.language },
      rating_id: s.finals.at(-1)?.rating_id ?? null,
      code_version: "mock",
      stage: "paudit",
      stageIdx: 0,
    };
    s.runs.push(run);
    s.first_run_id ??= run.run_id;
    s.holdFirstStart = false;
    s.error = null;
    s.state = "running";
    s.step = "paudit";
    s.progress = RUN_START_PROGRESS;
    this.count(s.uid, "eval");
    this.emit(s);
    return run;
  }

  startRun(uid: string, sid: string, body: S["RunRequest"]): S["RunStarted"] {
    const s = this.own(uid, sid);
    if (s.state === "report_ready" || s.reports.length > 0)
      bad(409, "rating_final", "The rating is final once the report is ready.");
    const ok = s.state === "awaiting_input" || s.state === "failed";
    if (s.state === "failed" && s.error && BAD_FILE_CODES.has(s.error.code))
      bad(409, "invalid_state", "A run cannot start in this state.");
    if (!ok || !s.flags.transcript_ready || !s.flags.speaker_confirmed)
      bad(409, "invalid_state", "A run cannot start in this state.");
    if (body.n_runs != null && (!Number.isInteger(body.n_runs) || body.n_runs < 1 || body.n_runs > 5))
      invalidParam("n_runs must be an integer from 1 to 5");
    if (body.preset != null && !PRESETS.includes(body.preset)) invalidParam("preset is not allowed");
    s.holdFirstStart = false; // the user pressed Start
    this.checkCap(uid, "eval");
    for (const o of this.sessions.values()) {
      if (o.uid === uid && o.state === "running") {
        bad(429, "concurrent_runs", "A rating is already running.", [
          { code: "concurrent_runs", message: "A rating is already running." },
        ]);
      }
    }
    // Try again re-runs the SAME submission: the client's preset / n_runs are ignored
    const prior = s.state === "failed" ? s.runs.at(-1) : undefined;
    const run = this.createRun(s, prior ? { preset: prior.preset, n_runs: prior.n_runs } : body);
    return { run_id: run.run_id, session: { id: s.id, status: s.state } };
  }

  listRuns(uid: string, sid: string): S["RunView"][] {
    return this.own(uid, sid).runs.map(publicRun);
  }

  getRun(uid: string, runId: string): S["RunView"] {
    for (const s of this.sessions.values()) {
      const r = s.uid === uid ? s.runs.find((x) => x.run_id === runId) : undefined;
      if (r) return publicRun(r);
    }
    return notFound();
  }

  listReports(uid: string, sid: string): S["ReportListItem"][] {
    return this.own(uid, sid).reports.map(({ version, report_id, run_id, created_at }) => ({
      version,
      report_id,
      run_id,
      created_at,
    }));
  }

  getReport(uid: string, sid: string, version: number): Report {
    const r = this.own(uid, sid).reports.find((x) => x.version === version);
    return r ? structuredClone(r.report) : notFound();
  }

  /** The API's `ReportView`: the report JSON wrapped with its version metadata. */
  getReportView(uid: string, sid: string, version: number): S["ReportView"] {
    const r = this.own(uid, sid).reports.find((x) => x.version === version);
    if (!r) return notFound();
    return {
      version: r.version,
      report_id: r.report_id,
      run_id: r.run_id,
      created_at: r.created_at,
      report_schema_version: r.report.schema_version,
      report: structuredClone(r.report) as unknown as S["ReportView"]["report"],
    };
  }

  // ---- API key (one active key per user; create revokes the old one) -----

  getApiKey(uid: string): S["ApiKeyInfo"] {
    const k = this.apiKeys.get(uid);
    return k ? { active: true, key_id: k.key_id, created: k.created, last_used_at: null } : { active: false };
  }

  createApiKey(uid: string): S["ApiKeyCreated"] {
    this.n += 1;
    const key_id = `k${this.n}abc`;
    const created = this.now().toISOString();
    this.apiKeys.set(uid, { key_id, created });
    return { key_id, api_key: `onolys_${key_id}_mock${this.n}secret`, created };
  }

  deleteApiKey(uid: string): void {
    this.apiKeys.delete(uid);
  }

  getUsage(uid: string): S["Usage"] {
    const period = (kind: CapKind, p: CapPeriod) => ({
      used: this.used(uid, kind, p),
      cap: this.caps[kind][p],
      resets_at: this.resetsAt(),
    });
    const kindUsage = (kind: CapKind) => ({ day: period(kind, "day") });
    return { eval: kindUsage("eval"), interview: kindUsage("interview") };
  }

  // ---- the worker, one step at a time -------------------------------------

  /** Advance one worker step for a session. Returns false when nothing moved. */
  advance(sid: string): boolean {
    const s = this.sessions.get(sid);
    if (!s) return false;

    if (s.state === "validating") {
      const code = this.injected(s, VALIDATE_FAILS);
      if (code) this.fail(s, code, "validate");
      else {
        s.state = "transcribing";
        s.step = "transcribe";
        s.progress = 20;
        this.emit(s);
      }
      return true;
    }

    if (s.state === "transcribing") {
      const code = this.injected(s, TRANSCRIBE_FAILS);
      if (code) this.fail(s, code, "transcribe");
      else {
        s.flags.transcript_ready = true;
        s.state = "awaiting_input";
        s.step = null;
        s.progress = 40;
        this.emit(s);
        this.maybeStartFirstRun(s);
      }
      return true;
    }

    if (s.state === "running") {
      const run = s.runs.at(-1);
      if (!run) return false;
      const stage = STAGES[run.stageIdx];
      if (stage === "paudit" && this.titleIs(s, "fail-paudit")) {
        run.status = "failed";
        this.fail(s, "internal_error", "paudit");
        return true;
      }
      s.progress += STAGE_WEIGHT[stage];
      run.stageIdx += 1;
      if (run.stageIdx < STAGES.length) {
        run.stage = STAGES[run.stageIdx];
        s.step = run.stage;
      } else {
        run.status = "done";
        run.stage = null;
        this.finishRun(s, run);
      }
      this.emit(s);
      return true;
    }
    return false;
  }

  private finishRun(s: SessionRec, run: RunRec): void {
    const rating = s.finals.find((r) => r.rating_id === run.rating_id);
    const created_at = this.now().toISOString();
    const report = reportFor({
      edge: this.titleIs(s, "utf8-edge"),
      hasRating: rating?.has_content ?? false,
      reasonsFailed: this.titleIs(s, "fail-eaudit"),
      tipsFailed: this.titleIs(s, "fail-tips"),
      createdAt: created_at,
    });
    report.header.n_runs = run.n_runs;
    report.header.preset = run.preset ?? null;
    s.reports.push({
      version: s.reports.length + 1,
      report_id: this.id("rp"),
      run_id: run.run_id,
      created_at,
      report,
    });
    s.state = "report_ready";
    s.step = null;
  }

  /** Advance until the session stops on a human wait or a terminal state. */
  settle(sid: string): void {
    for (let i = 0; i < 50 && this.advance(sid); i++);
  }

  /** One step for every session that is moving on its own (browser auto-advance). */
  advanceAll(): void {
    for (const sid of [...this.sessions.keys()]) this.advance(sid);
  }
}

function publicRun({ stageIdx: _ignored, ...run }: RunRec): S["RunView"] {
  void _ignored;
  return { ...run };
}

function cardHasContent(card: RatingCard): boolean {
  const g = Object.values(card.globals ?? {}).some(
    (x) => (x.score ?? null) !== null || !!x.reason?.trim() || !!x.example?.text?.trim(),
  );
  const c = Object.values(card.counts ?? {}).some(
    (x) => (x.count ?? null) !== null || !!x.note?.trim(),
  );
  return g || c || !!card.notes?.trim();
}

/** Hard limits (SP04 R2): UI only warns, the API rejects with `rating_invalid`. */
function validateCard(card: RatingCard, final: boolean): void {
  type Issue = { field: string; issue: "required" | "too_long" | "out_of_range" };
  const errors: Issue[] = [];
  const max = (path: string, v: unknown, n: number) => {
    if (typeof v === "string" && [...v].length > n) errors.push({ field: path, issue: "too_long" });
  };
  if (final && !(typeof card.change_goal === "string" && card.change_goal.trim()))
    errors.push({ field: "change_goal", issue: "required" });
  max("change_goal", card.change_goal, 1000);
  max("notes", card.notes, 3000);
  for (const [id, g] of Object.entries(card.globals ?? {})) {
    if (g.score != null && (!Number.isInteger(g.score) || g.score < 1 || g.score > 5))
      errors.push({ field: `globals/${id}/score`, issue: "out_of_range" });
    max(`globals/${id}/reason`, g.reason, 1000);
    max(`globals/${id}/example/text`, g.example?.text, 1000);
  }
  for (const [id, c] of Object.entries(card.counts ?? {})) {
    if (c.count != null && (!Number.isInteger(c.count) || c.count < 0))
      errors.push({ field: `counts/${id}/count`, issue: "out_of_range" });
    max(`counts/${id}/note`, c.note, 1000);
  }
  if (errors.length)
    bad(
      422,
      "rating_invalid",
      "The rating card is invalid.",
      errors.map((e) => ({ code: "rating_invalid", field: e.field, issue: e.issue, message: `${e.field}: ${e.issue}` })),
    );
}
