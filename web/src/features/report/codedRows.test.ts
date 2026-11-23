import { describe, expect, it } from "vitest";
import { buildCodedRows, countsFromRows, evidenceUtterances } from "./codedRows";

type T = { id: string; speaker: string; role?: "clinician" | "client" | null; text: string };
const turns: T[] = [
  { id: "t1", speaker: "spk_0", role: "clinician", text: "What would you like to change?" },
  { id: "t2", speaker: "spk_1", role: "client", text: "I want to walk more." },
  { id: "t3", speaker: "spk_0", role: "clinician", text: "Thanks, see you next week." },
  { id: "t4", speaker: "spk_0", role: "clinician", text: "You want to walk more, and it is yours to plan." },
  { id: "t5", speaker: "spk_9", role: null, text: "Something said." },
];
const inst = (turn_id: string, start: number, end: number, id: string, rationale = "r") =>
  ({ turn_id, start, end, quote: "q", id, rationale });
const beh = (item_id: string, instances: ReturnType<typeof inst>[]) =>
  ({ item_id, instances, instances_total: instances.length });
const report = (behaviours: unknown[], subject = "spk_0") =>
  ({ behaviours, header: { subject_speaker: subject } }) as never;
const tr = turns as never;

describe("buildCodedRows", () => {
  it("joins several codes on one turn in instance order, with labels, groups and rationales", () => {
    const rows = buildCodedRows(
      tr,
      report([
        beh("cr", [inst("t4", 0, 22, "a", "reflects")]),
        beh("emphasize_autonomy", [inst("t4", 24, 47, "b", "autonomy")]),
      ]),
    );
    const r = rows[3];
    expect(r.n).toBe(4);
    expect(r.speaker).toBe("P");
    expect(r.codes.map((c) => c.item_id)).toEqual(["cr", "emphasize_autonomy"]);
    expect(r.codes[0]).toMatchObject({ label: "Complex Reflection", group: "Questions & reflections" });
    expect(r.codes[1]).toMatchObject({ label: "Emphasize Autonomy", group: "MI-adherent" });
    expect(r.why).toEqual(["reflects", "autonomy"]);
    expect(r.uncoded).toBe(false);
  });

  it("client turn with no codes is not flagged uncoded", () => {
    const r = buildCodedRows(tr, report([]))[1];
    expect(r).toMatchObject({ speaker: "C", codes: [], why: [], uncoded: false, notCoded: false });
  });

  it("flags an uncoded practitioner turn, and 'Not coded' only when in opts.notCoded", () => {
    const plain = buildCodedRows(tr, report([]));
    expect(plain[2]).toMatchObject({ uncoded: true, notCoded: false });
    const nc = buildCodedRows(tr, report([]), { notCoded: new Set(["t3"]) });
    expect(nc[2]).toMatchObject({ uncoded: true, notCoded: true });
    expect(nc[0]).toMatchObject({ uncoded: true, notCoded: false });
  });

  it("drops an instance whose turn is missing, without breaking other rows", () => {
    const rows = buildCodedRows(tr, report([beh("sr", [inst("gone", 0, 3, "x"), inst("t1", 0, 5, "y")])]));
    expect(rows).toHaveLength(5);
    expect(rows[0].codes.map((c) => c.item_id)).toEqual(["sr"]);
  });

  it("skips an instance with a bad span", () => {
    const rows = buildCodedRows(
      tr,
      report([beh("sr", [inst("t1", 5, 2, "a"), inst("t1", -1, 3, "b"), inst("t1", 0, 999, "c"), inst("t1", 0, 4, "d")])]),
    );
    expect(rows[0].codes).toHaveLength(1);
    expect(rows[0].why).toEqual(["r"]);
  });

  it("falls back to the raw speaker id when role is null; subject speaker counts as practitioner", () => {
    const rows = buildCodedRows(tr, report([]));
    expect(rows[4].speaker).toBe("spk_9");
    expect(rows[4].uncoded).toBe(false);
    const rows2 = buildCodedRows(
      [{ id: "a", speaker: "spk_0", role: null, text: "hi there" }] as never,
      report([], "spk_0"),
    );
    expect(rows2[0]).toMatchObject({ speaker: "spk_0", uncoded: true });
  });

  it("falls back to the item id for unknown codes", () => {
    const r = buildCodedRows(tr, report([beh("zzz", [inst("t1", 0, 3, "a")])]))[0];
    expect(r.codes[0]).toMatchObject({ item_id: "zzz", label: "zzz" });
  });

  it("recomputes counts from rows (dropped and bad-span instances do not count)", () => {
    const rows = buildCodedRows(
      tr,
      report([
        beh("sr", [inst("t1", 0, 4, "a"), inst("t4", 0, 4, "b"), inst("gone", 0, 1, "c"), inst("t4", 9, 1, "d")]),
        beh("question", [inst("t1", 5, 9, "e")]),
      ]),
    );
    expect(countsFromRows(rows)).toEqual({ sr: 2, question: 1 });
  });
});

describe("evidenceUtterances", () => {
  const g = { onolys: { evidence: [{ turn_id: "t4" }, { turn_id: "t2" }, { turn_id: "nope" }, { turn_id: "t4" }] } };
  it("maps turn ids to sorted unique 1-based numbers, skipping unknown ids", () => {
    expect(evidenceUtterances(g as never, tr)).toEqual([2, 4]);
  });
  it("returns [] when no evidence or none known", () => {
    expect(evidenceUtterances({ onolys: { evidence: [] } } as never, tr)).toEqual([]);
    expect(evidenceUtterances({} as never, tr)).toEqual([]);
    expect(evidenceUtterances({ onolys: { evidence: [{ turn_id: "x" }] } } as never, tr)).toEqual([]);
  });
});
