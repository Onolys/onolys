import type { ReactNode, RefObject } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@onolys/ui";
import "./ui.css";

/** Modal wrapper (design rule 2: configs and details open in a popup). The trigger is the caller's verb-labelled button; pass `returnFocus` when the trigger is not a Radix trigger. */
export function AppDialog({ open, onOpenChange, title, description, footer, returnFocus, children }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: ReactNode;
  footer?: ReactNode; returnFocus?: RefObject<HTMLElement | null>; children?: ReactNode;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="ui-dialog" onCloseAutoFocus={returnFocus ? (event) => { event.preventDefault(); returnFocus.current?.focus(); } : undefined}>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description ? <DialogDescription>{description}</DialogDescription> : null}
      </DialogHeader>
      <div className="ui-dialog-body">{children}</div>
      {footer ? <DialogFooter>{footer}</DialogFooter> : null}
    </DialogContent>
  </Dialog>;
}
