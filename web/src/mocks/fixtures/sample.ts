/**
 * Public `/sample` fixture: a made-up 54-utterance drinking role-play (27 practitioner),
 * copied from the approved report mockup. Separate from the older walking fixtures (PRD D4).
 */
import type { Explanation, Line, Report } from "../../api/report";
import type { Turn } from "./transcripts";

type Code =
  | "gi" | "persuade" | "persuade_permission" | "question" | "sr" | "cr"
  | "affirm" | "seek_collab" | "emphasize_autonomy" | "confront";

/**
 * [speaker P|C, text, [code, rationale, span?][]]; one code instance per entry. `span` is the
 * substring of the utterance the code covers; omitted means the whole utterance.
 */
type Row = [sp: "P" | "C", text: string, codes: [Code, string, string?][]];

const ROWS: Row[] = [
  ["P", "Thanks for making time. To start, what has been on your mind about your drinking?", [["question", "Open question that invites the client's view"]]],
  ["C", "Honestly, it's crept up. I used to have a glass or two on weekends and now it's most nights.", []],
  ["P", "It's become part of your regular week, and that has caught your attention.", [["cr", "'caught your attention' adds meaning"]]],
  ["C", "Yes, a bit.", []],
  ["P", "What made you notice it?", [["question", "Open question that asks for the client's reasons"]]],
  ["C", "My sister joked about how many bottles are in the recycling, and a coworker asked if I was okay after a team dinner. It stung a bit.", []],
  ["P", "Those comments landed, and they made you stop and look.", [["cr", "'landed' adds meaning about how the comments felt"]]],
  ["C", "Sort of. I wouldn't say I'm worried though. They're probably exaggerating.", []],
  ["P", "Other people sound alarmed, but to you it's not that serious.", [["cr", "Adds the contrast between others' alarm and the client's view"]]],
  ["C", "Right. I still do my job and I'm not missing school pickups or anything.", []],
  ["P", "What do you think they're seeing?", [["question", "Open question about what others notice"]]],
  ["C", "That I pour bigger glasses than I used to, and I start earlier in the evening.", []],
  ["P", "So the amount and the timing have both shifted.", [["sr", "Restates the client's words with little added"]]],
  ["C", "Yeah.", []],
  ["P", "How does that sit with you?", [["question", "Open question about the client's own reaction"]]],
  ["C", "Mixed. Mornings are rough lately. I'm foggy until about ten and I snapped at my kid last week.", []],
  ["P", "The foggy mornings bother you, though you wouldn't call it a crisis.", [["cr", "'bother you' adds a feeling the client did not state"]]],
  ["C", "No, not a crisis. But I hated that I snapped at my kid. That's not me.", []],
  ["P", "You snapped at your child.", [["sr", "Repeats what the client said and adds nothing"]]],
  ["C", "Yeah. Anyway, I do like my wine. It's how I unwind after work, and work has been stressful.", []],
  ["P", "Drinking is how you unwind, and the stress at work has been pushing it up.", [["cr", "Links drinking to unwinding and work stress"]]],
  ["C", "That's exactly it. I don't want to give it up. Maybe I just need to cut down to what I used to do.", []],
  ["P", "Cutting down is what you have in mind.", [["sr", "Repeats the client's plan"]]],
  ["C", "Mm-hm.", []],
  ["P", "That tends not to last. Most people slide back to where they started.", [["confront", "Disagrees with the client's idea and discourages it"]]],
  ["C", "What do you mean? I managed it before.", []],
  ["P", "Since you ask, many people who try cutting back drift to their old amounts within a few months, so stopping tends to hold up better.", [["persuade_permission", "Persuade with permission because client asked what was meant"]]],
  ["C", "So you're saying quitting is the only option?", []],
  ["P", "It's your call and nobody else can make it, but stopping has the better track record.", [["emphasize_autonomy", "'your call'", "It's your call and nobody else can make it"], ["persuade_permission", "Persuade with permission because client asked", "but stopping has the better track record."]]],
  ["C", "I don't agree. I was fine at that level, so why can't I go back to it?", []],
  ["P", "Because it crept up once, so it can again. You should really think about quitting for good.", [["persuade", "Argues for quitting without the client asking"]]],
  ["C", "That feels like you're telling me what to do.", []],
  ["P", "Fair enough. It's your decision, not mine. If you did go with cutting down, what would that look like for you?", [["emphasize_autonomy", "'your decision'", "It's your decision, not mine."], ["question", "Asks for the client's own plan", "If you did go with cutting down, what would that look like for you?"]]],
  ["C", "Maybe I could set a limit, like two glasses and nothing on weeknights. And write it down, since I didn't notice how much it grew.", []],
  ["P", "Tracking it is a clever step, since you spotted it grew without you noticing. How would you keep track?", [["affirm", "Names a strength in the client's idea", "Tracking it is a clever step, since you spotted it grew without you noticing."], ["question", "Asks how", "How would you keep track?"]]],
  ["C", "A note on my phone, I guess. A tally each night.", []],
  ["P", "I have a few ideas other people have found useful. Would you like to hear them?", [["seek_collab", "Asks permission before sharing ideas"]]],
  ["C", "Sure.", []],
  ["P", "Some people add a stress rating next to each tally, which shows what triggers drinking. Others pick a drink-free night and note how they feel. Would either suit you?", [["gi", "Neutral options with no push", "Some people add a stress rating next to each tally, which shows what triggers drinking. Others pick a drink-free night and note how they feel."], ["question", "Checks interest", "Would either suit you?"]]],
  ["C", "The stress rating, definitely. That's the part I keep coming back to. I'd rather deal with it now than end up having to quit completely.", []],
  ["P", "You'd rather act early, while you still have choices, than be forced into a bigger change later.", [["cr", "Adds meaning: acting early keeps choices open"]]],
  ["C", "Right. And I could still have a glass at dinner.", []],
  ["P", "You'd still enjoy it, just in smaller amounts.", [["sr", "Restates the client's wish"]]],
  ["C", "Yeah. I'm starting to see it's maybe more than I thought.", []],
  ["P", "You're noticing it more now, and it matters to you.", [["cr", "'it matters to you' adds meaning"]]],
  ["C", "It does. I'm just worried that stress will make me slip.", []],
  ["P", "Stress is the part you're unsure how to handle.", [["sr", "Rephrases the client's worry"]]],
  ["C", "Yes.", []],
  ["P", "It's great that you spotted stress as a trigger. If you're open to it, we can plan for that next time.", [["affirm", "Praises noticing the trigger", "It's great that you spotted stress as a trigger."], ["seek_collab", "Asks to plan together", "If you're open to it, we can plan for that next time."]]],
  ["C", "Okay. For now I just track my drinks and my stress?", []],
  ["P", "Yes, try the tally and the stress rating for a week and see what shows up. I'll give you a sheet to use.", [["persuade_permission", "Persuade with permission because client asked what to do"]]],
  ["C", "Okay.", []],
  ["P", "Great. Thanks for coming in today.", []],
  ["C", "Thanks.", []],
];

export const drinkingSampleTurns: Turn[] = ROWS.map(([sp, text], i) => ({
  id: `t${i + 1}`,
  speaker: sp === "P" ? "spk_0" : "spk_1",
  role: sp === "P" ? "clinician" : "client",
  start_ms: i * 9000,
  end_ms: i * 9000 + 8000,
  text,
}));

/** Practitioner turns shown as "Not coded" rather than "—" (closing pleasantry). */
export const drinkingSampleNotCoded: ReadonlySet<string> = new Set(["t53"]);

const turnOf = (n: number): Turn => drinkingSampleTurns[n - 1];
const cpLen = (s: string) => Array.from(s).length;

/** Line covering `span` (a substring of utterance `n`; default the whole utterance), code-point offsets. */
function lineOf(n: number, span?: string): Line {
  const t = turnOf(n);
  if (span === undefined) return { turn_id: t.id, start: 0, end: cpLen(t.text), quote: t.text };
  const at = t.text.indexOf(span);
  if (at < 0) throw new Error(`sample span not found in utterance ${n}: ${span}`);
  const start = cpLen(t.text.slice(0, at));
  return { turn_id: t.id, start, end: start + cpLen(span), quote: span };
}

const NO_EXPLANATION: Explanation = { headline: "", body: [], onolys_lines: [], clinician_support_lines: [] };
const NOT_RATED = { signed: null, abs: null, direction: null, status: "not_rated" as const };
const stats = (v: number) => ({ mean: v, min: v, max: v, values: [v] });

const GLOBALS: { id: string; label: string; score: number; reason: string; utts: number[] }[] = [
  {
    id: "cct",
    label: "Cultivating Change Talk",
    score: 2,
    reason:
      "The client gives reasons to act (utterances 18, 40), but only utterance 41 builds on them; 19 and 31 miss or work against them.",
    utts: [18, 40, 41, 19, 31],
  },
  {
    id: "sst",
    label: "Softening Sustain Talk",
    score: 2,
    reason:
      "Reflections at 9, 17 and 21 respect the ambivalence, but the confront at 25 and persuasion at 31 draw pushback (26, 30, 32).",
    utts: [9, 17, 21, 25, 31, 26, 30, 32],
  },
  {
    id: "partnership",
    label: "Partnership",
    score: 2,
    reason:
      "The practitioner pushes quitting over the client's aim (25, 27, 31) until the client says they feel told what to do (32); autonomy is restored at 33.",
    utts: [25, 27, 31, 32, 33],
  },
  {
    id: "empathy",
    label: "Empathy",
    score: 3,
    reason:
      "Reflections at 3, 7 and 21 show real effort to grasp the client's view and stress, but 25 and 31 set it aside.",
    utts: [3, 7, 21, 25, 31],
  },
];

const COUNTS: { id: Code; label: string }[] = [
  { id: "gi", label: "Giving Information" },
  { id: "persuade", label: "Persuade" },
  { id: "persuade_permission", label: "Persuade with Permission" },
  { id: "question", label: "Question" },
  { id: "sr", label: "Simple Reflection" },
  { id: "cr", label: "Complex Reflection" },
  { id: "affirm", label: "Affirm" },
  { id: "seek_collab", label: "Seek Collaboration" },
  { id: "emphasize_autonomy", label: "Emphasize Autonomy" },
  { id: "confront", label: "Confront" },
];

const behaviours: Report["behaviours"] = COUNTS.map((c) => {
  const instances: Report["behaviours"][number]["instances"] = [];
  ROWS.forEach(([, , codes], i) => {
    for (const [code, rationale, span] of codes) {
      if (code !== c.id) continue;
      instances.push({ id: `${c.id}-${instances.length + 1}`, ...lineOf(i + 1, span), rationale });
    }
  });
  return {
    item_id: c.id,
    clinician_count: null,
    onolys_count: stats(instances.length),
    instances,
    instances_total: instances.length,
    diff: { ...NOT_RATED },
    explanation: { ...NO_EXPLANATION },
  };
});

const count = (id: Code) => behaviours.find((b) => b.item_id === id)!.instances.length;
const sr = count("sr");
const cr = count("cr");
const q = count("question");
const tech = (GLOBALS[0].score + GLOBALS[1].score) / 2;
const rel = (GLOBALS[2].score + GLOBALS[3].score) / 2;
const mia = count("seek_collab") + count("affirm") + count("emphasize_autonomy");
const mina = count("confront") + count("persuade");
const NOTE = "Reference levels, not pass marks.";

const scorecard: Report["scorecard"] = [
  ...GLOBALS.map((g) => ({ id: g.id, kind: "global" as const, label: g.label, v: g.score })),
  ...COUNTS.map((c) => ({ id: c.id, kind: "count" as const, label: c.label, v: count(c.id) })),
].map((x) => ({
  item_id: x.id,
  kind: x.kind,
  label: x.label,
  clinician: { value: null },
  onolys: { value: x.v, ...stats(x.v) },
  diff: { ...NOT_RATED },
}));

const globals: Report["globals"] = GLOBALS.map((g) => ({
  item_id: g.id,
  onolys: { score: g.score, source: "model", reason: g.reason, evidence: g.utts.map((u) => lineOf(u)) },
  clinician: { value: null },
  diff: { ...NOT_RATED },
  explanation: { ...NO_EXPLANATION },
}));

function tip(rank: number, item_id: Code, utt: number, observation: string, tryText: string, example: string, why: string) {
  const l = lineOf(utt);
  return {
    rank,
    item_id,
    observation,
    quote: { turn_id: l.turn_id, start: l.start, end: l.end, text: l.quote },
    alternative: `${tryText} “${example}”`,
    why_it_matters: why,
  };
}

export const drinkingSampleReport: Report = {
  schema_version: "0.0.1",
  created_at: "2026-11-20T09:30:00.000Z",
  header: {
    change_goal: "Cut down on drinking",
    protocol: { id: "miti", version: "4.2.1", pack_hash: "sample0000", label: "MITI 4.2.1" },
    language: "en-US",
    coded_span: null,
    subject_speaker: "spk_0",
    n_runs: 1,
    models: { miti_code: "mock-model-a", miti_globals: "mock-model-b", tips: "mock-model-a" },
    stt: null,
    preset: "default",
    code_version: "mock",
    params: {},
    has_clinician_rating: false,
    rating_coverage: { rated: 0, total: 14 },
  },
  layout: [
    { section: "scorecard", title: "Scorecard" },
    { section: "disagreements", title: "Where Onolys disagrees" },
    { section: "globals", title: "Global scores" },
    { section: "behaviours", title: "Behaviour counts" },
    { section: "summaries", title: "Summary measures" },
    { section: "reasons_audit", title: "Your reasons, checked" },
    { section: "tips", title: "Tips" },
    { section: "method", title: "About this report" },
  ],
  scorecard,
  globals,
  behaviours,
  summaries: [
    { id: "technical", label: "Technical Global", clinician: null, onolys: { value: tech, label: "below_fair" }, reference: { fair: 3, good: 4 }, note: NOTE },
    { id: "relational", label: "Relational Global", clinician: null, onolys: { value: rel, label: "below_fair" }, reference: { fair: 3.5, good: 4 }, note: NOTE },
    { id: "pct_cr", label: "% Complex Reflections", clinician: null, onolys: { value: cr / (sr + cr), label: "good" }, reference: { fair: 0.4, good: 0.5 }, note: NOTE },
    { id: "reflection_question_ratio", label: "Reflection-to-Question Ratio", clinician: null, onolys: { value: (sr + cr) / q, label: "fair" }, reference: { fair: 1, good: 2 }, note: NOTE },
    { id: "total_mia", label: "Total MI-Adherent", clinician: null, onolys: { value: mia, label: null }, reference: null, note: "" },
    { id: "total_mina", label: "Total MI Non-Adherent", clinician: null, onolys: { value: mina, label: null }, reference: null, note: "" },
  ],
  reasons_audit: { status: "skipped", items: [] },
  tips: [
    tip(
      1, "confront", 25,
      "Arguing against cutting down closed the client off",
      "Reflect what the client wants instead of arguing against it.",
      "You'd like to keep wine in your life and bring it back to where it was.",
      "Disagreeing makes people defend their view. The client pushed back right away (utterances 26 and 30).",
    ),
    tip(
      2, "persuade", 31,
      "Persuading without asking made the client feel told what to do",
      "Ask permission, share what you have seen, then ask what the client makes of it.",
      "Would it be okay if I shared what I've seen when people cut back? ... What do you make of that?",
      "Advice that is asked for is heard. Unasked advice led to \"you're telling me what to do\" (utterance 32).",
    ),
    tip(
      3, "sr", 19,
      "A simple reflection missed the client's reason to change",
      "Reflect the value behind the words with a complex reflection.",
      "Snapping at your child doesn't fit the parent you want to be, and the foggy mornings are part of that.",
      "Reflecting the client's own reasons draws out more change talk. The client had just said \"That's not me\".",
    ),
  ],
  method: {
    statement:
      "Onolys reads the transcript against the MITI 4.2.1 coding manual and scores the four global ratings and the behaviour counts. Each code in the transcript shows the reason it was given.",
    limits: [
      "Onolys reads the transcript only. Tone of voice, pauses and body language are not available to it.",
      "Speaker labels and timestamps come from automatic transcription and can contain errors.",
      "Behaviour counts depend on where each utterance is split, so small differences are expected.",
    ],
    not_official_miti_coding: true,
    citation:
      "Moyers, T. B., Manuel, J. K., & Ernst, D. (2014). Motivational Interviewing Treatment Integrity Coding Manual 4.2.1.",
  },
  aggregates: { globals_compared: 0, avg_abs_global_difference: null, within_one_share: null, counts_flagged: null },
  warnings: [],
  run_info: {
    evaluation: { engine: "evaluation", code_version: "mock" },
    miti: { engine: "miti", code_version: "mock", span: null },
  },
};
