import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { describe, expect, it } from "vitest";
import { drinkingSampleTurns } from "./sample";
import { drinkingSampleReport, edgeReport, noRatingReport, noTipsReport, reasonsFailedReport, sampleReport } from ".";

/** Validates every report fixture against the real contract (SP03 report.schema.json). */
const repoRoot = resolve(__dirname, "../../../..");
const schema = JSON.parse(readFileSync(resolve(repoRoot, "engines/miti/src/onolys_miti/data/report.schema.json"), "utf8"));
const ajv = new Ajv2020({ allErrors: true, strict: false });
const validate = ajv.compile(schema);

const packFixture = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(repoRoot, `engines/miti/src/onolys_miti/data/fixtures/evaluation/${name}`), "utf8"));

const fixtures: [string, unknown][] = [
  ["sample (N=1, rated)", sampleReport],
  ["drinking sample (54 utterances)", drinkingSampleReport],
  ["no-rating", noRatingReport],
  ["reasons_audit failed", reasonsFailedReport],
  ["no tips", noTipsReport],
  ["utf-8 edge", edgeReport],
  ["pack report_full.json", packFixture("report_full.json")],
  ["pack report_partial.json", packFixture("report_partial.json")],
  ["pack report_no_rating.json", packFixture("report_no_rating.json")],
];

describe.each(fixtures)("report.schema.json validates: %s", (_name, report) => {
  it("is valid", () => {
    const ok = validate(report);
    expect(ok ? [] : validate.errors?.map((e) => `${e.instancePath} ${e.message}`)).toEqual([]);
  });
});

describe("validator sanity", () => {
  it("rejects an unknown extra field (additionalProperties: false)", () => {
    expect(validate({ ...(sampleReport as object), bogus: 1 })).toBe(false);
  });
});

describe("public sample consistency", () => {
  it("records the whole fictional session and its short-session warning", () => {
    const duration = Math.ceil(Math.max(...drinkingSampleTurns.map((t) => t.end_ms ?? t.start_ms ?? 0)) / 1000);
    expect(drinkingSampleReport.header.coded_span).toBeNull();
    expect(drinkingSampleReport.run_info.miti.span).toEqual({ mode: "whole", duration_s: duration, seed: "sample" });
    expect(duration).toBeLessThan(600);
    expect(drinkingSampleReport.warnings).toEqual([
      { code: "short_session" },
      { code: "reflection_before_client_speech" },
    ]);
  });

  it("keeps every code, global and tip quotation anchored to the source text", () => {
    const lines = [
      ...drinkingSampleReport.behaviours.flatMap((b) => b.instances),
      ...drinkingSampleReport.globals.flatMap((g) => g.onolys.evidence),
      ...drinkingSampleReport.tips.map((t) => ({ ...t.quote, quote: t.quote.text })),
    ];
    for (const line of lines) {
      const source = drinkingSampleTurns.find((t) => t.id === line.turn_id);
      expect(source).toBeDefined();
      expect(Array.from(source!.text).slice(line.start, line.end).join("")).toBe(line.quote);
    }
  });
});
