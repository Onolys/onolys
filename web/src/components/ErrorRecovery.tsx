import { useEffect, useRef } from "react";
import { ApiError } from "../api/errors";

/** Recovery copy is fixed: never expose exception messages or response bodies. */
export function ErrorRecovery({ error, status, reload = () => window.location.reload() }: {
  error?: unknown;
  status?: number;
  reload?: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const httpStatus = error instanceof ApiError ? error.status : status;
  const reference = error instanceof ApiError && /^[A-Za-z0-9._-]{1,64}$/.test(error.requestId ?? "")
    ? error.requestId : undefined;
  const notFound = httpStatus === 404;
  return (
    <section role="alert" className="grid gap-4 rounded-lg border border-border bg-card p-6 text-card-foreground">
      <h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold">{notFound ? "Page not found" : "Something went wrong"}</h1>
      <p>{notFound ? "We couldn't find this page. Check the link or go back to the start." : "We couldn't load this page. Reload to try again, or go back to the start."}</p>
      {httpStatus ? <p className="text-sm text-muted-foreground">Error {httpStatus}</p> : null}
      {reference ? <p className="break-all text-sm text-muted-foreground">Reference: {reference}</p> : null}
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" className="min-h-11 rounded-md border border-border px-4 py-2 font-medium focus-visible:outline-2 focus-visible:outline-offset-2" onClick={reload}>Reload page</button>
        <a href="/" className="text-primary underline underline-offset-4">Back to the start</a>
      </div>
    </section>
  );
}
