// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ChartFrame } from "./ChartFrame";
import { ComboTag } from "./ComboTag";

afterEach(cleanup);

const table = <table><caption>Values</caption><tbody><tr><th scope="row">A</th><td>2</td></tr></tbody></table>;

it("ChartFrame shows title, one-sentence caption, legend slot and chart", () => {
  const { container } = render(<ChartFrame title="Cost vs accuracy" caption="Lower is better." legend={<span>LEGEND</span>} table={table}><svg aria-label="plot" /></ChartFrame>);
  expect(screen.getByRole("heading", { name: "Cost vs accuracy" })).toBeTruthy();
  expect(screen.getByText("Lower is better.")).toBeTruthy();
  expect(screen.getByText("LEGEND")).toBeTruthy();
  expect(screen.getByLabelText("plot")).toBeTruthy();
  expect(container.querySelector(".table-scroll")).toBeNull();
});

it("ChartFrame keeps the data table behind a collapsed 'Show data' disclosure", () => {
  render(<ChartFrame title="T" caption="C" table={table}><svg /></ChartFrame>);
  const toggle = screen.getByRole("button", { name: "Show data" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("Values")).toBeNull();
  fireEvent.click(toggle);
  expect(screen.getByText("Values")).toBeTruthy();
});

it("ComboTag renders letter + shape + colour class", () => {
  const { container } = render(<ComboTag index={1} />);
  const tag = container.querySelector(".ui-combo-tag")!;
  expect(tag.textContent).toBe("B");
  expect((tag as HTMLElement).style.color).toBe("rgb(180, 83, 9)");
  expect(screen.getByRole("img", { name: "Combo B" })).toBe(tag);
  expect(tag.querySelector("svg")!.getAttribute("data-shape")).toBe("square");
  expect(tag.getAttribute("aria-label")).toBe("Combo B");
});

it("ComboTag wraps palette after 7 and honours an explicit letter", () => {
  const { container } = render(<ComboTag index={7} letter="Z" />);
  const tag = container.querySelector(".ui-combo-tag")!;
  expect(tag.textContent).toBe("Z");
  expect((tag as HTMLElement).style.color).toBe("rgb(11, 95, 90)");
  expect(tag.querySelector("svg")!.getAttribute("data-shape")).toBe("circle");
});
