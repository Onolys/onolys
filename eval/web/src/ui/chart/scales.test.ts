import { expect, it } from "vitest";
import { bandScale, clampScore, linearScale, SCORE_TICKS, scoreScale } from "./scales";

it("scoreScale maps the 1-5 domain onto the range", () => {
  const s = scoreScale(0, 400);
  expect([1, 2, 3, 4, 5].map((v) => s(v))).toEqual([0, 100, 200, 300, 400]);
  expect(s.domain()).toEqual([1, 5]);
});

it("scoreScale supports an inverted (vertical) range", () => {
  const s = scoreScale(200, 0);
  expect(s(1)).toBe(200);
  expect(s(5)).toBe(0);
});

it("SCORE_TICKS are exactly the integers 1-5 and match the scale ticks", () => {
  expect(SCORE_TICKS).toEqual([1, 2, 3, 4, 5]);
  expect(scoreScale(0, 100).ticks(4)).toEqual(SCORE_TICKS);
});

it("clampScore keeps values inside 1-5", () => {
  expect([0, 1, 3.2, 5, 9].map(clampScore)).toEqual([1, 1, 3.2, 5, 5]);
});

it("linearScale produces round ticks and nice domains", () => {
  const s = linearScale({ domain: [0, 97], range: [0, 100], nice: true });
  expect(s.domain()).toEqual([0, 100]);
  expect(s.ticks(5)).toEqual([0, 20, 40, 60, 80, 100]);
});

it("bandScale gives each category a slot with padding", () => {
  const s = bandScale({ domain: ["A", "B", "C"], range: [0, 300], padding: 0 });
  expect(s("B")).toBe(100);
  expect(s.bandwidth()).toBe(100);
});
