/** The jsdom shims in setup.ts let @onolys/ui's Radix components render. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@onolys/ui";
import { describe, expect, it } from "vitest";

describe("jsdom shims for @onolys/ui", () => {
  it("provides ResizeObserver, matchMedia, pointer capture and DOMRect", () => {
    expect(typeof ResizeObserver).toBe("function");
    expect(typeof window.matchMedia("(prefers-reduced-motion: reduce)").matches).toBe("boolean");
    expect(typeof Element.prototype.hasPointerCapture).toBe("function");
    expect(typeof Element.prototype.setPointerCapture).toBe("function");
    expect(typeof Element.prototype.releasePointerCapture).toBe("function");
    expect(typeof DOMRect).toBe("function");
  });

  it("opens and closes a Dialog by role", async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Title</DialogTitle>
          <DialogDescription>Body</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByRole("dialog", { name: "Title" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a DropdownMenu and exposes menuitems", async () => {
    const user = userEvent.setup();
    render(
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button>Menu</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Settings</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    await user.click(screen.getByRole("button", { name: "Menu" }));
    expect(await screen.findByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
  });
});
