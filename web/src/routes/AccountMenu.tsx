import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@onolys/ui";

/** Avatar button at the far right of the header; opens email, Settings and Sign out (shared nonmodal DropdownMenu). */
export function AccountMenu({ email, onSignOut }: { email: string | null; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  // Menu pattern: opening (pointer or keyboard) moves focus to the first item. Radix focuses the content on pointer open.
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      const el = contentRef.current;
      if (el && (document.activeElement === el || document.activeElement === document.body)) el.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [open]);

  const initial = (email?.trim()[0] ?? "?").toUpperCase();

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Button asChild size="icon" className="rounded-full font-semibold">
        <DropdownMenuTrigger aria-label="Account menu">{initial}</DropdownMenuTrigger>
      </Button>
      <DropdownMenuContent
        ref={contentRef}
        align="end"
        loop
        // Tab leaves the menu: close it (Radix keeps focus on the trigger rather than tabbing on).
        onKeyDown={(e) => {
          if (e.key === "Tab") setOpen(false);
        }}
        className="min-w-56 max-w-80"
      >
        {email && <DropdownMenuLabel className="font-normal break-words text-muted-foreground">{email}</DropdownMenuLabel>}
        {email && <DropdownMenuSeparator />}
        <DropdownMenuItem asChild>
          <Link to="/settings">Settings</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onSignOut}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
