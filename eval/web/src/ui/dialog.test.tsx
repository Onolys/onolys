// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { AppDialog } from "./AppDialog";
import { CopyField } from "./CopyField";

afterEach(cleanup);

function Harness({ withRef = false }: { withRef?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  return <>
    <button ref={ref} onClick={() => setOpen(true)}>Open config</button>
    <AppDialog open={open} onOpenChange={setOpen} title="Run configuration" description="Saved settings" footer={<button>Done</button>} returnFocus={withRef ? ref : undefined}>
      <p>Body text</p>
    </AppDialog>
  </>;
}

it("opens with a labelled title, body and footer; closes via the close button", async () => {
  render(<Harness />);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Open config" }));
  const dialog = await screen.findByRole("dialog", { name: "Run configuration" });
  expect(dialog.textContent).toContain("Body text");
  expect(screen.getByRole("button", { name: "Done" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /close/i }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("Escape closes and focus returns to the trigger", async () => {
  render(<Harness withRef />);
  const trigger = screen.getByRole("button", { name: "Open config" });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = await screen.findByRole("dialog");
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});

it("CopyField shows label and value and copies the value", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  render(<CopyField label="Run ID" value="run_abc123" />);
  expect(screen.getByText("Run ID")).toBeTruthy();
  const val = screen.getByText("run_abc123");
  expect(val.className).toContain("ui-copyfield-value");
  fireEvent.click(screen.getByRole("button", { name: /copy/i }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("run_abc123"));
  expect(await screen.findByText("Copied")).toBeTruthy();
});
