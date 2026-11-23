import type { components } from "../../api/schema";
import type { GlobalEntry, Report } from "../../api/report";
import { codePointLength } from "../../lib/codepoints";

type Turn = components["schemas"]["TranscriptTurnV1"];

/** One code on a row; label and colour come from `codeMeta`. */
export interface CodedChip {
  item_id: string;
}

export type TurnsState =
  | { status: "loading" }
  | { status: "error"; retry?: () => void }
  | { status: "ready"; turns: readonly Turn[] };

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

const validSpan = (text: string, start: number, end: number) =>
  Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= codePointLength(text);

/** Join transcript turns with report instances into one row per turn. Pure. */
export function buildCodedRows(turns: readonly Turn[], report: Report, opts: CodedRowsOpts = {}): CodedRow[] {
  const byTurn = new Map<string, { item_id: string; start: number; rationale: string }[]>();
  const textOf = new Map(turns.map((t) => [t.id, t.text]));
  for (const b of report.behaviours ?? []) {
    for (const i of b.instances ?? []) {
      const text = textOf.get(i.turn_id);
      if (text === undefined || !validSpan(text, i.start, i.end)) continue;
      const e = byTurn.get(i.turn_id) ?? [];
      e.push({ item_id: b.item_id, start: i.start, rationale: i.rationale });
      byTurn.set(i.turn_id, e);
    }
  }
  const subject = report.header?.subject_speaker;
  return turns.map((t, idx) => {
    // Instance (text) order; Array.sort is stable, so ties keep encounter order.
    const e = [...(byTurn.get(t.id) ?? [])].sort((x, y) => x.start - y.start);
    const codes: CodedChip[] = e.map((x) => ({ item_id: x.item_id }));
    const speaker = t.role === "clinician" ? "P" : t.role === "client" ? "C" : t.speaker;
    const practitioner = t.role === "clinician" || (t.role == null && subject !== undefined && t.speaker === subject);
    const uncoded = practitioner && codes.length === 0;
    return {
      n: idx + 1,
      turn_id: t.id,
      speaker,
      text: t.text,
      codes,
      why: e.map((x) => x.rationale),
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
