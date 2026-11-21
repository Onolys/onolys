import { describe, expect, it } from "vitest";
import { blockingPeriod, evalCapCode, formatBlockingReset, remaining, usageLeftText, type Period, type Usage } from "./usage";

const p = (used: number, cap: number): Period => ({ used, cap, resets_at: "2026-12-01T00:00:00.000Z" });
const usage = (e: [Period, Period], i: [Period, Period] = [p(0, 5), p(0, 30)]): Usage => ({
  eval: { day: e[0], month: e[1] },
  interview: { day: i[0], month: i[1] },
});

describe("remaining", () => {
  it("is cap minus used", () => expect(remaining(p(2, 5))).toBe(3));
  it("clamps at 0 when over the cap", () => expect(remaining(p(7, 5))).toBe(0));
  it("is 0 for a zero cap", () => expect(remaining(p(0, 0))).toBe(0));
});

describe("blockingPeriod", () => {
  it("is null while usage is loading", () => expect(blockingPeriod(undefined, "eval")).toBeNull());
  it("is null when both periods have room", () => expect(blockingPeriod(usage([p(1, 10), p(1, 100)]), "eval")).toBeNull());
  it("is the day when only the day is exhausted", () => {
    expect(blockingPeriod(usage([p(10, 10), p(10, 100)]), "eval")?.name).toBe("day");
  });
  it("is the month when only the month is exhausted", () => {
    expect(blockingPeriod(usage([p(1, 10), p(100, 100)]), "eval")?.name).toBe("month");
  });
  it("prefers the month when both are exhausted", () => {
    expect(blockingPeriod(usage([p(10, 10), p(100, 100)]), "eval")?.name).toBe("month");
  });
  it("reads the requested kind only", () => {
    const u = usage([p(10, 10), p(10, 100)], [p(0, 5), p(0, 30)]);
    expect(blockingPeriod(u, "interview")).toBeNull();
    expect(blockingPeriod(u, "eval")?.name).toBe("day");
  });
  it("maps to the eval error code", () => {
    expect(evalCapCode({ name: "day", period: p(1, 1) })).toBe("daily_cap_reached");
    expect(evalCapCode({ name: "month", period: p(1, 1) })).toBe("monthly_cap_reached");
  });
});

describe("usageLeftText", () => {
  it("reads 'N of M left today'", () => expect(usageLeftText(p(2, 5), "day")).toBe("3 of 5 left today"));
  it("reads 'N of M left this month'", () => expect(usageLeftText(p(12, 30), "month")).toBe("18 of 30 left this month"));
  it("clamps at 0", () => expect(usageLeftText(p(9, 5), "day")).toBe("0 of 5 left today"));
});

describe("formatBlockingReset", () => {
  it("is undefined with no blocking period", () => expect(formatBlockingReset(null)).toBeUndefined());
  it("is a date for the month cap", () => {
    expect(formatBlockingReset({ name: "month", period: p(1, 1) })).toMatch(/Dec\s+1|1\s+Dec/);
  });
  it("is a time for the day cap", () => {
    expect(formatBlockingReset({ name: "day", period: p(1, 1) })).toMatch(/\d/);
  });
});
