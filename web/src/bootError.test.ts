import { describe, expect, it, vi } from "vitest";
import { renderBootError } from "./bootError";

describe("renderBootError", () => {
  it("shows a fallback with a working reload button", () => {
    const root = document.createElement("div");
    const reload = vi.fn();
    renderBootError(root, reload);
    expect(root.textContent).toContain("Can't start the app. Reload the page.");
    root.querySelector("button")!.click();
    expect(reload).toHaveBeenCalledOnce();
  });
});
