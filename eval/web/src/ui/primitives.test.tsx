// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Chip } from "./Chip";
import { CopyButton } from "./CopyButton";
import { Note } from "./Note";
import { StatTile } from "./StatTile";
import { SummaryCard } from "./SummaryCard";

afterEach(cleanup);

it.each(["success", "warning", "danger", "neutral", "muted", "info"] as const)("Chip tone %s has its class and an icon alongside the text", (tone) => {
  const { container } = render(<Chip tone={tone}>Label</Chip>);
  const chip = container.querySelector(".ui-chip")!;
  expect(chip.classList.contains(`ui-chip-${tone}`)).toBe(true);
  expect(chip.textContent).toBe("Label");
  const icon = chip.querySelector("svg");
  expect(icon).toBeTruthy();
  expect(icon!.getAttribute("aria-hidden")).toBe("true");
});

it("Chip never relies on colour alone: icon can be replaced but not dropped by default", () => {
  const { container } = render(<Chip tone="danger" icon={<span data-testid="custom" />}>Failed</Chip>);
  expect(screen.getByTestId("custom")).toBeTruthy();
  expect(container.querySelector("svg")).toBeNull();
});

it("StatTile shows label, value and sub; zero is muted", () => {
  const { container, rerender } = render(<StatTile label="Failed" value={0} sub="of 12" />);
  const tile = container.querySelector(".ui-stat")!;
  expect(tile.textContent).toContain("Failed");
  expect(tile.textContent).toContain("of 12");
  expect(container.querySelector(".ui-stat-value")!.classList.contains("ui-zero")).toBe(true);
  rerender(<StatTile label="Failed" value={3} />);
  expect(container.querySelector(".ui-stat-value")!.classList.contains("ui-zero")).toBe(false);
});

it("SummaryCard renders a small title, big value and muted sub, zero muted", () => {
  const { container } = render(<SummaryCard title="Cost" value="0" sub="estimated" />);
  expect(screen.getByText("Cost").classList.contains("ui-summary-title")).toBe(true);
  expect(container.querySelector(".ui-summary-value")!.classList.contains("ui-zero")).toBe(true);
  expect(screen.getByText("estimated").classList.contains("ui-summary-sub")).toBe(true);
});

it("Note is a small muted paragraph", () => {
  render(<Note>Only scored sessions.</Note>);
  const note = screen.getByText("Only scored sessions.");
  expect(note.tagName).toBe("P");
  expect(note.classList.contains("ui-note")).toBe(true);
});

it("CopyButton writes the value to the clipboard and shows Copied", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  render(<CopyButton value="run-123" />);
  const button = screen.getByRole("button", { name: "Copy" });
  expect(button.textContent).not.toContain("run-123");
  await act(async () => { fireEvent.click(button); });
  expect(writeText).toHaveBeenCalledWith("run-123");
  expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
});
