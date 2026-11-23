import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { UsageCountView, usageTone } from "./UsageCount";

describe("usageTone", () => {
  it.each([
    [0, 20, "text-destructive"],
    [4, 20, "text-destructive"],
    [4.99, 20, "text-destructive"],
    [5, 20, "text-warning"],
    [9, 20, "text-warning"],
    [10, 20, "text-success"],
    [20, 20, "text-success"],
    [0, 0, "text-destructive"],
    [1, 5, "text-destructive"],
    [2, 5, "text-warning"],
    [3, 5, "text-success"],
  ])("%i of %i -> %s", (left, cap, cls) => {
    expect(usageTone(left, cap)).toBe(cls);
  });
});

describe("UsageCountView", () => {
  const period = { used: 0, cap: 5, resets_at: "2030-01-01T00:00:00Z" } as never;

  it("shows x/y coloured by remaining and is focusable with an accessible name", () => {
    render(<UsageCountView period={period} />);
    const el = screen.getByText("5/5");
    expect(el.className).toContain("text-success");
    const trigger = screen.getByRole("button", { name: "5 of 5 left today" });
    expect(trigger).toContainElement(el);
  });

  it("uses warning and destructive colours", () => {
    const { rerender } = render(<UsageCountView period={{ used: 3, cap: 5, resets_at: "" } as never} />);
    expect(screen.getByText("2/5").className).toContain("text-warning");
    rerender(<UsageCountView period={{ used: 5, cap: 5, resets_at: "" } as never} />);
    expect(screen.getByText("0/5").className).toContain("text-destructive");
  });

  it("shows the tooltip on keyboard focus and on hover", async () => {
    render(<UsageCountView period={period} />);
    await userEvent.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("5 of 5 left today");
    await userEvent.tab();
    expect(screen.queryByRole("tooltip")).toBeNull();
    await userEvent.hover(screen.getByRole("button", { name: "5 of 5 left today" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("5 of 5 left today");
  });
});
