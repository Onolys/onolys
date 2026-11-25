import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { DeleteDialog } from "./DeleteDialog";

function Harness({ busy = false, onConfirm = () => {} }: { busy?: boolean; onConfirm?: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <ConfirmDialog
      open={open}
      busy={busy}
      title="Cancel this session?"
      description="Processing stops."
      confirmLabel="Cancel session"
      cancelLabel="Keep processing"
      confirmVariant="default"
      onConfirm={onConfirm}
      onCancel={() => setOpen(false)}
    />
  );
}

describe("ConfirmDialog", () => {
  it("renders its copy, focuses the cancel button first, and confirms", async () => {
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    expect(screen.getByRole("alertdialog", { name: "Cancel this session?" })).toBeInTheDocument();
    expect(screen.getByText("Processing stops.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep processing" })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Cancel session" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("closes on Escape and on the cancel button when idle", async () => {
    const { unmount } = render(<Harness />);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    unmount();
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Keep processing" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("blocks Escape and Cancel while a request is in flight", async () => {
    render(<Harness busy />);
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep processing" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel session" })).toBeDisabled();
  });
});

describe("DeleteDialog (wrapper)", () => {
  it("keeps its copy, focus on Cancel, and confirm", async () => {
    const onConfirm = vi.fn();
    render(<DeleteDialog open busy={false} onConfirm={onConfirm} onCancel={() => {}} />);
    const dialog = screen.getByRole("alertdialog", { name: "Delete this session?" });
    expect(dialog).toHaveAttribute("data-slot", "delete-dialog");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("does not call onCancel on Escape while busy", async () => {
    const onCancel = vi.fn();
    render(<DeleteDialog open busy onConfirm={() => {}} onCancel={onCancel} />);
    await userEvent.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
