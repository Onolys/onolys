import { useEffect, useRef } from "react";
import { Link } from "react-router";
import type { MappedAuthError } from "../errors";
import { withNext } from "../next";

export const ERROR_ID = "form-error";

/** Error summary: role=alert, takes focus when it appears or changes (R8 a11y). */
export function ErrorSummary({ error, search }: { error: MappedAuthError; search: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [error]);
  return (
    <div role="alert" id={ERROR_ID} tabIndex={-1} ref={ref} className="form-error">
      <p>{error.message}</p>
      {error.offerLogin && (
        <p>
          <Link to={withNext("/login", search)}>Log in instead</Link>
        </p>
      )}
    </div>
  );
}
