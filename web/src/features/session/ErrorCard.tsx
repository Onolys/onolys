import { Alert, AlertDescription } from "@onolys/ui";
import type { ReactNode } from "react";
import { messageForCode } from "../../api/errors";

/** Plain message per error code plus the reference id support can look up (PRD R4 Failure, R8). */
export function ErrorCard({
  code,
  reference,
  resetsAt,
  children,
}: {
  code: string | undefined;
  reference?: string;
  resetsAt?: string;
  children?: ReactNode;
}) {
  return (
    <Alert variant="destructive" className="border-destructive">
      <AlertDescription>
        <p className="font-semibold">{messageForCode(code, { resetsAt })}</p>
        {reference ? <p className="text-muted-foreground">Reference: {reference}</p> : null}
        {children ? <div className="flex flex-wrap gap-3">{children}</div> : null}
      </AlertDescription>
    </Alert>
  );
}
