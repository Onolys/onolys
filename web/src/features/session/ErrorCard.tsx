import { Alert, AlertDescription } from "@onolys/common";
import type { ReactNode } from "react";
import { messageForCode } from "../../api/errors";

/** Plain message per error code plus the reference id support can look up. */
export function ErrorCard({
  code,
  reference,
  resetsAt,
  message,
  note,
  children,
}: {
  code: string | undefined;
  /** Overrides the per-code message (failure cards, where the kind picks the copy). */
  message?: string;
  note?: string;
  reference?: string;
  resetsAt?: string;
  children?: ReactNode;
}) {
  return (
    <Alert variant="destructive" className="border-destructive">
      <AlertDescription>
        <p className="font-semibold">{message ?? messageForCode(code, { resetsAt })}</p>
        {note ? <p>{note}</p> : null}
        {reference ? <p className="text-muted-foreground">Reference: {reference}</p> : null}
        {children ? <div className="flex flex-wrap gap-3">{children}</div> : null}
      </AlertDescription>
    </Alert>
  );
}
