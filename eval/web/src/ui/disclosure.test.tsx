// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { Disclosure } from "./Disclosure";

afterEach(cleanup);

it("is collapsed by default: aria-expanded false and content not in the DOM", () => {
  render(<Disclosure label="Show data"><p>Inside</p></Disclosure>);
  const btn = screen.getByRole("button", { name: "Show data" });
  expect(btn.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("Inside")).toBeNull();
});

it("toggles open and closed on click", () => {
  render(<Disclosure label="Show data"><p>Inside</p></Disclosure>);
  const btn = screen.getByRole("button", { name: "Show data" });
  fireEvent.click(btn);
  expect(btn.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("Inside")).toBeTruthy();
  expect(btn.getAttribute("aria-controls")).toBe(screen.getByText("Inside").parentElement!.id);
  fireEvent.click(btn);
  expect(screen.queryByText("Inside")).toBeNull();
});

it("defaultOpen starts expanded", () => {
  render(<Disclosure label="Show data" defaultOpen><p>Inside</p></Disclosure>);
  expect(screen.getByRole("button", { name: "Show data" }).getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("Inside")).toBeTruthy();
});

it("is keyboard operable: a focusable native button (Enter/Space click it natively)", () => {
  render(<Disclosure label="Show data"><p>Inside</p></Disclosure>);
  const btn = screen.getByRole("button", { name: "Show data" });
  expect(btn.tagName).toBe("BUTTON");
  expect(btn.getAttribute("type")).toBe("button");
  expect(btn.tabIndex).toBe(0);
  btn.focus();
  expect(document.activeElement).toBe(btn);
});
