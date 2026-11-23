import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusChip, type ChipTone } from "./StatusChip";

describe("StatusChip", () => {
  it.each<ChipTone>(["progress", "wait", "done", "failed", "agree", "differs", "flagged", "neutral"])("keeps its own text and data-tone for %s", (tone) => {
    render(<StatusChip tone={tone}>Custom text</StatusChip>);
    const chip = screen.getByText("Custom text");
    expect(chip).toHaveAttribute("data-tone", tone);
    expect(chip).toHaveAttribute("data-slot", "badge");
  });

  it("adds tone colours from semantic tokens only", () => {
    render(<StatusChip tone="failed">Failed</StatusChip>);
    expect(screen.getByText("Failed").className).toMatch(/text-score-low/);
    expect(screen.getByText("Failed").className).not.toMatch(/gray-/);
  });
});
