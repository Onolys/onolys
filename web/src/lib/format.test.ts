import { describe, expect, it } from "vitest";
import { formatResetTime } from "./format";

describe("formatResetTime", () => {
  it("includes the time zone so a bare clock time is not ambiguous (E23)", () => {
    const out = formatResetTime("2026-11-22T09:00:00Z") ?? "";
    expect(out).toMatch(/\d{1,2}:\d{2}/);
    expect(out).toMatch(/[A-Za-z]{2,}|GMT|UTC|[+-]\d/); // a zone name or offset after the time
    expect(out.replace(/^\d{1,2}:\d{2}\s?(AM|PM)?/i, "").trim()).not.toBe("");
  });
});
