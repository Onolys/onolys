import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RetryButton } from "./RetryButton";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("RetryButton countdown", () => {
  it("starts at Retry (5), aria-disabled, and counts down to Retry", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} />);
    const btn = screen.getByRole("button", { name: "Retry (5)" });
    expect(btn).toHaveAttribute("aria-disabled", "true");
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByRole("button", { name: "Retry (4)" })).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(3000));
    expect(screen.getByRole("button", { name: "Retry (1)" })).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(1000));
    const ready = screen.getByRole("button", { name: "Retry" });
    expect(ready).not.toHaveAttribute("aria-disabled", "true");
  });

  it("ignores clicks while counting and calls onRetry once enabled", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} />);
    act(() => void screen.getByRole("button", { name: "Retry (5)" }).click());
    expect(onRetry).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(5000));
    act(() => void screen.getByRole("button", { name: "Retry" }).click());
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not reset on re-render, only on remount", () => {
    const { rerender, unmount } = render(<RetryButton onRetry={() => {}} />);
    act(() => void vi.advanceTimersByTime(5000));
    rerender(<RetryButton onRetry={() => {}} />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    unmount();
    render(<RetryButton onRetry={() => {}} />);
    expect(screen.getByRole("button", { name: "Retry (5)" })).toBeInTheDocument();
  });

  it("stays disabled while a retry is pending", () => {
    const onRetry = vi.fn();
    render(<RetryButton onRetry={onRetry} pending />);
    act(() => void vi.advanceTimersByTime(5000));
    act(() => void screen.getByRole("button", { name: /Retry/ }).click());
    expect(onRetry).not.toHaveBeenCalled();
  });
});
