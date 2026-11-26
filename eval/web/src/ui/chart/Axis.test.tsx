// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Axis } from "./Axis";
import { scoreScale, SCORE_TICKS } from "./scales";
import { CHART_GUTTER, COMBO_PALETTE, COMBO_SHAPES, comboColor } from "./theme";

afterEach(cleanup);

it("left axis renders 1-5 tick labels inside a fixed gutter", () => {
  const { container } = render(<svg><Axis orientation="left" scale={scoreScale(200, 0)} tickValues={SCORE_TICKS} /></svg>);
  const labels = [...container.querySelectorAll("text")].map((t) => t.textContent);
  expect(labels).toEqual(["1", "2", "3", "4", "5"]);
  expect(container.querySelector(".visx-axis-left")!.getAttribute("transform")).toBe(`translate(${CHART_GUTTER.left}, 0)`);
});

it("bottom axis is placed at the given y and carries an accessible label", () => {
  const { container } = render(<svg><Axis orientation="bottom" scale={scoreScale(0, 300)} tickValues={SCORE_TICKS} top={180} label="Score" /></svg>);
  expect(container.innerHTML).toContain("180");
  expect(container.textContent).toContain("Score");
});

it("combo palette has distinct colours and shapes for A-D and a letter key per combo", () => {
  expect(new Set(COMBO_PALETTE.slice(0, 4)).size).toBe(4);
  expect(new Set(COMBO_SHAPES.slice(0, 4)).size).toBe(4);
  expect(comboColor(0)).toBe(COMBO_PALETTE[0]);
  expect(comboColor(COMBO_PALETTE.length + 1)).toBe(COMBO_PALETTE[1]);
});
