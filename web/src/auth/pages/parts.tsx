import { useEffect, useRef, type ComponentProps, type ReactNode } from "react";
import { Link } from "react-router";
import { Alert, AlertDescription, Input, Label } from "@onolys/ui";
import type { MappedAuthError } from "../errors";
import { withNext } from "../next";

export const ERROR_ID = "form-error";

/** Text link styling shared by the auth screens (semantic tokens only). */
export const LINK = "text-primary underline underline-offset-4";
/** Page heading and form layout shared by the auth screens. */
export const H1 = "m-0 text-2xl font-semibold";
export const FORM = "mt-4 grid max-w-sm grid-cols-1 gap-4 break-words [&_p]:m-0";
/** Stack for non-form states (results, expired links): heading, notice, action. */
export const STACK = "grid max-w-sm grid-cols-1 gap-4 break-words [&_p]:m-0";
export const BTN = "border-0";
export const NOTE = "text-sm text-muted-foreground";

/** Error summary: role=alert, takes focus when it appears or changes (R8 a11y). */
export function ErrorSummary({ error, search }: { error: MappedAuthError; search: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [error]);
  return (
    <Alert
      variant="destructive"
      id={ERROR_ID}
      tabIndex={-1}
      ref={ref}
      className="border-destructive focus-visible:ring-[3px] focus-visible:ring-ring"
    >
      <AlertDescription>
        <p>{error.message}</p>
        {error.offerLogin && (
          <p>
            <Link to={withNext("/login", search)} className={LINK}>
              Log in instead
            </Link>
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}

/** Non-error notice (role=status): info/success styling via semantic tokens, since Alert only has default/destructive. */
export function StatusNote({ children }: { children: ReactNode }) {
  return (
    <Alert role="status" className="bg-muted text-foreground">
      <AlertDescription className="text-foreground">{children}</AlertDescription>
    </Alert>
  );
}

/** Label + Input pair; `id` links them so the accessible name stays the label text. */
export function Field({ label, id, ...input }: { label: string; id: string } & ComponentProps<typeof Input>) {
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="min-h-0 text-base font-semibold">
        {label}
      </Label>
      <Input id={id} {...input} />
    </div>
  );
}
