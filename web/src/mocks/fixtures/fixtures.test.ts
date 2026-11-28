import { describe, expect, it } from "vitest";
import type { Line, Report } from "../../api/report";
import type { components } from "../../api/schema";
import {
  drinkingSampleNotCoded,
  drinkingSampleReport,
  drinkingSampleTurns,
  edgeReport,
  edgeTranscript,
  noRatingReport,
  noTipsReport,
  reportFor,
  reasonsFailedReport,
  sampleReport,
  sampleTranscript,
  threeSpeakerTranscript,
} from ".";
import { buildCodedRows, countsFromRows, evidenceUtterances } from "../../features/report/codedRows";

type Turn = components["schemas"]["TranscriptView"]["turns"][number];

const cpSlice = (text: string, start: number, end: number) =>
  Array.from(text).slice(start, end).join("");

const SECTIONS = ["scorecard", "disagreements", "globals", "behaviours", "summaries", "reasons_audit", "tips", "method"];

function allLines(r: Report): Line[] {
  const lines: Line[] = [];
  for (const g of r.globals) {
    lines.push(...g.onolys.evidence, ...g.explanation.onolys_lines, ...g.explanation.clinician_support_lines);
  }
  for (const b of r.behaviours) {
    lines.push(...b.instances, ...b.explanation.onolys_lines, ...b.explanation.clinician_support_lines);
  }
  for (const it of r.reasons_audit.items) for (const c of it.claims) lines.push(...c.evidence);
  for (const t of r.tips) lines.push({ ...t.quote, quote: t.quote.text });
  return lines;
}

const variants: [string, Report, Turn[]][] = [
  ["sample (N=1, rated)", sampleReport, sampleTranscript],
  ["no-rating", noRatingReport, sampleTranscript],
  ["reasons_audit failed", reasonsFailedReport, sampleTranscript],
  ["no tips", noTipsReport, sampleTranscript],
  ["utf-8 edge", edgeReport, edgeTranscript],
];

describe.each(variants)("report fixture: %s", (_name, report, turns) => {
  it("every quote equals the transcript slice at its code-point offsets", () => {
    const lines = allLines(report);
    expect(lines.length).toBeGreaterThan(0);
    for (const l of lines) {
      const turn = turns.find((t) => t.id === l.turn_id);
      expect(turn, `turn ${l.turn_id}`).toBeDefined();
      expect(cpSlice(turn!.text, l.start, l.end)).toBe(l.quote);
    }
  });
});

describe("sample report content", () => {
  it("is N=1 and covers the 14 MITI items from the layout order", () => {
    expect(sampleReport.header.n_runs).toBe(1);
    expect(sampleReport.scorecard.map((s) => s.item_id)).toEqual([
      "cct", "sst", "partnership", "empathy",
      "gi", "persuade", "persuade_permission", "question", "sr", "cr", "affirm", "seek_collab", "emphasize_autonomy", "confront",
    ]);
    expect(sampleReport.layout.map((l) => l.section)).toEqual(SECTIONS);
    expect(sampleReport.header.stt?.provider).toBeTruthy();
    expect(sampleReport.header.preset).toBeTruthy();
    expect(sampleReport.header.code_version).toBeTruthy();
  });

  it("has a global that differs, a count that is flagged, and a count that only differs", () => {
    const g = sampleReport.globals.filter((x) => x.diff.status === "differs");
    expect(g.length).toBeGreaterThan(0);
    expect(g[0].explanation.headline).toBeTruthy();
    expect(g[0].explanation.onolys_lines.length).toBeGreaterThan(0);
    expect(g[0].explanation.clinician_support_lines.length).toBeGreaterThan(0);
    const flagged = sampleReport.behaviours.filter((x) => x.diff.status === "flagged");
    const differs = sampleReport.behaviours.filter((x) => x.diff.status === "differs");
    expect(flagged.length).toBeGreaterThan(0);
    expect(differs.length).toBeGreaterThan(0);
    expect(flagged[0].explanation.headline).toBeTruthy();
    expect(differs[0].explanation.headline).toBe("");
    expect(flagged.some((b) => b.instances_total > b.instances.length)).toBe(true);
  });

  it("includes reasons audit (ran), 3 tips, and reference levels", () => {
    expect(sampleReport.reasons_audit.status).toBe("ran");
    expect(sampleReport.tips).toHaveLength(3);
    expect(sampleReport.summaries.every((s) => s.reference !== null && s.reference.good > s.reference.fair)).toBe(true);
  });

  it("is synthetic: no PHI-like content", () => {
    const text = JSON.stringify(sampleReport) + JSON.stringify(sampleTranscript);
    expect(text).not.toMatch(/@|\b\d{3}[- ]\d{3,4}[- ]\d{4}\b/);
  });
});

describe("no-rating report", () => {
  it("has Onolys values only", () => {
    expect(noRatingReport.header.has_clinician_rating).toBe(false);
    expect(noRatingReport.scorecard.every((s) => s.clinician.value === null)).toBe(true);
    expect(noRatingReport.scorecard.every((s) => s.diff.status === "not_rated")).toBe(true);
    expect(noRatingReport.scorecard.every((s) => s.onolys.value !== null)).toBe(true);
    expect(noRatingReport.reasons_audit.status).toBe("skipped");
    expect(noRatingReport.aggregates.avg_abs_global_difference).toBeNull();
    expect(noRatingReport.summaries.every((s) => s.clinician === null)).toBe(true);
    expect(noRatingReport.tips.length).toBeGreaterThan(0);
  });
});

describe("failure-variant reports", () => {
  it("reasons_audit failed keeps the rest of the report", () => {
    expect(reasonsFailedReport.reasons_audit).toEqual({ status: "failed", items: [] });
    expect(reasonsFailedReport.warnings.map((w) => w.code)).toContain("reasons_audit_failed");
    expect(reasonsFailedReport.scorecard).toEqual(sampleReport.scorecard);
    expect(reasonsFailedReport.tips).toEqual(sampleReport.tips);
  });

  it("no-tips report has an empty tips list and a warning", () => {
    expect(noTipsReport.tips).toEqual([]);
    expect(noTipsReport.warnings.map((w) => w.code)).toContain("tips_failed");
  });
});

describe("transcripts", () => {
  it("UTF-8 edge transcript has astral emoji, ZWJ sequences and combining marks", () => {
    const text = edgeTranscript.map((t) => t.text).join("\n");
    expect(text).toMatch(/[\u{1F300}-\u{1FAFF}]/u);
    expect(text).toContain("‍"); // ZWJ
    expect(text).toMatch(/\p{M}/u); // combining mark
    // UTF-16 length differs from code-point count => offsets must be code points
    expect(text.length).toBeGreaterThan(Array.from(text).length);
  });

  it("edge report instances sit after astral characters (offsets differ between UTF-16 and code points)", () => {
    const shifted = allLines(edgeReport).filter((l) => {
      const t = edgeTranscript.find((x) => x.id === l.turn_id)!;
      return t.text.slice(l.start, l.end) !== l.quote;
    });
    expect(shifted.length).toBeGreaterThan(0);
  });

  it("three-speaker transcript has exactly three speakers, each with at least 3 turns", () => {
    const counts = new Map<string, number>();
    for (const t of threeSpeakerTranscript) counts.set(t.speaker ?? "", (counts.get(t.speaker ?? "") ?? 0) + 1);
    expect([...counts.keys()].sort()).toEqual(["spk_0", "spk_1", "spk_2"]);
    for (const n of counts.values()) expect(n).toBeGreaterThanOrEqual(3);
  });

  it("turn ids are unique and sequential", () => {
    for (const ts of [sampleTranscript, edgeTranscript, threeSpeakerTranscript])
      expect(new Set(ts.map((t) => t.id)).size).toBe(ts.length);
  });
});

describe("run_info names the lean engine", () => {
  it.each([
    ["sample", sampleReport],
    ["no-rating", noRatingReport],
    ["reasons failed", reasonsFailedReport],
    ["no tips", noTipsReport],
    ["edge", edgeReport],
  ])("%s", (_n, r) => {
    expect(Object.keys(r.run_info).sort()).toEqual(["evaluation", "miti"]);
    expect(r.run_info.miti.span).toBeNull();
  });

  it("reportFor defaults to the no-rating fixture", () => {
    const r = reportFor({ hasRating: false });
    expect(r.header.has_clinician_rating).toBe(false);
    expect(r.run_info.miti.engine).toBe("miti");
  });
});

describe("drinking sample fixture (/sample)", () => {
  const r = drinkingSampleReport;
  const turns = drinkingSampleTurns;
  const rows = buildCodedRows(turns, r, { notCoded: drinkingSampleNotCoded });
  const val = (id: string) => r.scorecard.find((s) => s.item_id === id)?.onolys.value;

  it("has 54 turns, 27 practitioner, ids t1..t54, P=spk_0 clinician, C=spk_1 client", () => {
    expect(turns).toHaveLength(54);
    expect(turns.map((t) => t.id)).toEqual(Array.from({ length: 54 }, (_, i) => `t${i + 1}`));
    const p = turns.filter((t) => t.role === "clinician");
    expect(p).toHaveLength(27);
    expect(p.every((t) => t.speaker === "spk_0")).toBe(true);
    expect(turns.filter((t) => t.role === "client").every((t) => t.speaker === "spk_1")).toBe(true);
    expect(turns[0].text).toBe("Thanks for making time. To start, what has been on your mind about your drinking?");
    expect(r.header.subject_speaker).toBe("spk_0");
    expect(r.header.change_goal).toBe("Cut down on drinking");
  });

  it("counts recomputed from the coded rows equal the mockup table", () => {
    expect(countsFromRows(rows)).toEqual({
      question: 7, sr: 5, cr: 7, gi: 1, persuade: 1, persuade_permission: 3,
      affirm: 2, seek_collab: 2, emphasize_autonomy: 2, confront: 1,
    });
    for (const b of r.behaviours) {
      expect(b.onolys_count.mean).toBe(b.instances.length);
      expect(b.instances_total).toBe(b.instances.length);
      expect(b.instances.every((i) => i.rationale.length > 0)).toBe(true);
    }
  });

  it("totals: MI-adherent 6, non-adherent 2", () => {
    const c = countsFromRows(rows);
    expect(c.seek_collab + c.affirm + c.emphasize_autonomy).toBe(6);
    expect(c.confront + c.persuade).toBe(2);
  });

  it("multi-code rows keep one rationale per instance; turn 53 is the only not-coded turn", () => {
    for (const n of [29, 33, 35, 39, 49]) expect(rows[n - 1].codes).toHaveLength(2);
    expect(rows[28].codes.map((c) => c.item_id)).toEqual(["emphasize_autonomy", "persuade_permission"]);
    expect(rows[32].codes.map((c) => c.item_id)).toEqual(["emphasize_autonomy", "question"]);
    expect(rows[34].codes.map((c) => c.item_id)).toEqual(["affirm", "question"]);
    expect(rows[38].codes.map((c) => c.item_id)).toEqual(["gi", "question"]);
    expect(rows[48].codes.map((c) => c.item_id)).toEqual(["affirm", "seek_collab"]);
    expect(rows[28].why).toHaveLength(2);
    expect(rows.filter((x) => x.notCoded).map((x) => x.turn_id)).toEqual(["t53"]);
    expect(rows.filter((x) => x.uncoded).map((x) => x.turn_id)).toEqual(["t53"]);
    expect(rows.filter((x) => x.speaker === "C").every((x) => x.codes.length === 0)).toBe(true);
    expect(rows[0].why).toEqual(["Open question that invites the client's view"]);
  });

  it("globals are CCT 2, SST 2, PAR 2, EMP 3 with reasons and evidence", () => {
    expect([val("cct"), val("sst"), val("partnership"), val("empathy")]).toEqual([2, 2, 2, 3]);
    expect(r.globals.map((g) => g.onolys.score)).toEqual([2, 2, 2, 3]);
    expect(r.globals.every((g) => (g.onolys.reason ?? "").length > 0)).toBe(true);
    const ev = Object.fromEntries(r.globals.map((g) => [g.item_id, evidenceUtterances(g, turns)]));
    expect(ev).toEqual({
      cct: [18, 19, 31, 40, 41],
      sst: [9, 17, 21, 25, 26, 30, 31, 32],
      partnership: [25, 27, 31, 32, 33],
      empathy: [3, 7, 21, 25, 31],
    });
  });

  it("summaries match PRD req 16", () => {
    const s = Object.fromEntries(r.summaries.map((x) => [x.id, x]));
    expect(r.summaries).toHaveLength(6);
    expect(s.technical.onolys).toEqual({ value: 2, label: "below_fair" });
    expect(s.technical.reference).toEqual({ fair: 3, good: 4 });
    expect(s.relational.onolys).toEqual({ value: 2.5, label: "below_fair" });
    expect(s.relational.reference).toEqual({ fair: 3.5, good: 4 });
    expect(s.pct_cr.onolys.value).toBeCloseTo(7 / 12, 10);
    expect(s.pct_cr.onolys.label).toBe("good");
    expect(s.pct_cr.reference).toEqual({ fair: 0.4, good: 0.5 });
    expect(s.reflection_question_ratio.onolys.value).toBeCloseTo(12 / 7, 10);
    expect(s.reflection_question_ratio.onolys.label).toBe("fair");
    expect(s.reflection_question_ratio.reference).toEqual({ fair: 1, good: 2 });
    expect(s.total_mia.onolys).toEqual({ value: 6, label: null });
    expect(s.total_mia.reference).toBeNull();
    expect(s.total_mina.onolys).toEqual({ value: 2, label: null });
    expect(s.total_mina.reference).toBeNull();
    expect(r.summaries.every((x) => x.clinician === null)).toBe(true);
  });

  it("has no clinician rating and a skipped reasons audit", () => {
    expect(r.header.has_clinician_rating).toBe(false);
    expect(r.scorecard.every((x) => x.clinician.value === null && x.diff.status === "not_rated")).toBe(true);
    expect(r.reasons_audit).toEqual({ status: "skipped", items: [] });
  });

  it("3 tips by rank, quotes resolve inside their turns, evidence turn ids exist", () => {
    expect(r.tips.map((t) => [t.rank, t.item_id, t.quote.turn_id])).toEqual([
      [1, "confront", "t25"], [2, "persuade", "t31"], [3, "sr", "t19"],
    ]);
    expect(r.tips[0].observation).toBe("Arguing against cutting down closed the client off");
    expect(r.tips[2].quote.text).toBe("You snapped at your child.");
    for (const t of r.tips) {
      const turn = turns.find((x) => x.id === t.quote.turn_id)!;
      expect(cpSlice(turn.text, t.quote.start, t.quote.end)).toBe(t.quote.text);
      expect(t.alternative).toContain("\u201C");
      expect(t.why_it_matters.length).toBeGreaterThan(0);
    }
    const ids = new Set(turns.map((t) => t.id));
    const lines = allLines(r);
    for (const l of lines) {
      expect(ids.has(l.turn_id)).toBe(true);
      expect(cpSlice(turns.find((t) => t.id === l.turn_id)!.text, l.start, l.end)).toBe(l.quote);
    }
    for (const g of r.globals) expect(g.onolys.evidence.length).toBeGreaterThan(0);
  });
});
