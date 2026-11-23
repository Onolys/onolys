import type { components } from "../../api/schema";
import type { GlobalEntry, Report } from "../../api/report";
import { codePointLength } from "../../lib/codepoints";

type Turn = components["schemas"]["TranscriptTurnV1"];

export interface CodedChip {
  item_id: string;
  label: string;
  group: string;
}

export interface CodedRow {
  /** 1-based utterance number (turn order). */
  n: number;
  turn_id: string;
  speaker: string;
  text: string;
  codes: CodedChip[];
  /** One rationale per kept instance, in instance order. */
  why: string[];
  /** Practitioner turn with no codes. */
  uncoded: boolean;
  /** Uncoded and listed in `opts.notCoded`: show "Not coded" instead of "—". */
  notCoded: boolean;
}

export interface CodedRowsOpts {
  /** Turn ids shown as "Not coded" (sample only). */
  notCoded?: ReadonlySet<string>;
}

const G_INFO = "Information & persuasion";
const G_QR = "Questions & reflections";
const G_ADH = "MI-adherent";
const G_NON = "MI non-adherent";

/** Pack ids (engines/miti pack.yaml) -> short label and group. The report carries no labels. */
export const CODE_META: Record<string, { label: string; group: string }> = {
  gi: { label: "Giving Information", group: G_INFO },
  persuade: { label: "Persuade", group: G_INFO },
  persuade_permission: { label: "Persuade with Permission", group: G_INFO },
  question: { label: "Question", group: G_QR },
  sr: { label: "Simple Reflection", group: G_QR },
  cr: { label: "Complex Reflection", group: G_QR },
  affirm: { label: "Affirm", group: G_ADH },
  seek_collab: { label: "Seek Collaboration", group: G_ADH },
  emphasize_autonomy: { label: "Emphasize Autonomy", group: G_ADH },
  confront: { label: "Confront", group: G_NON },
};

function chip(item_id: string): CodedChip {
  const m = CODE_META[item_id];
  return { item_id, label: m?.label ?? item_id, group: m?.group ?? "" };
}

const validSpan = (text: string, start: number, end: number) =>
  Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= codePointLength(text);

/** Join transcript turns with report instances into one row per turn. Pure. */
export function buildCodedRows(turns: readonly Turn[], report: Report, opts: CodedRowsOpts = {}): CodedRow[] {
  const byTurn = new Map<string, { chips: CodedChip[]; why: string[] }>();
  const textOf = new Map(turns.map((t) => [t.id, t.text]));
  for (const b of report.behaviours ?? []) {
    for (const i of b.instances ?? []) {
      const text = textOf.get(i.turn_id);
      if (text === undefined || !validSpan(text, i.start, i.end)) continue;
      const e = byTurn.get(i.turn_id) ?? { chips: [], why: [] };
      e.chips.push(chip(b.item_id));
      e.why.push(i.rationale);
      byTurn.set(i.turn_id, e);
    }
  }
  const subject = report.header?.subject_speaker;
  return turns.map((t, idx) => {
    const e = byTurn.get(t.id);
    const codes = e?.chips ?? [];
    const speaker = t.role === "clinician" ? "P" : t.role === "client" ? "C" : t.speaker;
    const practitioner = t.role === "clinician" || (t.role == null && subject !== undefined && t.speaker === subject);
    const uncoded = practitioner && codes.length === 0;
    return {
      n: idx + 1,
      turn_id: t.id,
      speaker,
      text: t.text,
      codes,
      why: e?.why ?? [],
      uncoded,
      notCoded: uncoded && !!opts.notCoded?.has(t.id),
    };
  });
}

/** Per-code counts recomputed from the rows (what the table shows). */
export function countsFromRows(rows: readonly CodedRow[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) for (const c of r.codes) out[c.item_id] = (out[c.item_id] ?? 0) + 1;
  return out;
}

/** Sorted unique 1-based utterance numbers for a global's evidence lines; unknown turn ids skipped. */
export function evidenceUtterances(global: GlobalEntry, turns: readonly Turn[]): number[] {
  const index = new Map(turns.map((t, i) => [t.id, i + 1]));
  const ns = new Set<number>();
  for (const l of global.onolys?.evidence ?? []) {
    const n = index.get(l.turn_id);
    if (n !== undefined) ns.add(n);
  }
  return [...ns].sort((a, b) => a - b);
}
