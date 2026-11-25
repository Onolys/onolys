import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../AuthProvider";
import { EMAIL_PATTERN, isPopupCancel } from "../errors";
import { withNext } from "../next";
import { Button } from "@onolys/ui";
import { H1, LINK } from "../../components/classes";
import { ErrorSummary, FORM, Field, StatusNote } from "./parts";
import { useFormError } from "./useFormError";

/** Router state set by the password-reset flow. */
export interface LoginState {
  email?: string;
  passwordUpdated?: boolean;
}

export function Login({ showSignup = true }: { showSignup?: boolean }) {
  const { service } = useAuth();
  const { search, state } = useLocation();
  const from = (state ?? {}) as LoginState;
  const [busy, setBusy] = useState(false);
  const form = useFormError();

  // A failed redirect sign-in (mobile Google) lands back here with no other trace.
  useEffect(() => {
    void service.consumeRedirectError().then((code) => {
      if (code) form.fail({ code });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount; `form` is a fresh object each render
  }, [service]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    if (!email) return form.failWith("Enter your email.", "email");
    if (!EMAIL_PATTERN.test(email)) return form.failWith("Enter a valid email address.", "email");
    if (!password) return form.failWith("Enter your password.", "password");
    form.clear();
    setBusy(true);
    try {
      await service.signIn(email, password);
    } catch (err) {
      form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    if (busy) return;
    form.clear();
    setBusy(true);
    try {
      await service.signInWithGoogle();
    } catch (err) {
      if (!isPopupCancel(err)) form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className={H1}>Log in</h1>
      <form className={FORM} onSubmit={(e) => void onSubmit(e)} noValidate>
        {from.passwordUpdated && !form.error && <StatusNote>Password updated. Log in with your new password.</StatusNote>}
        {form.error && <ErrorSummary error={form.error} search={search} />}
        <Field label="Email" id="login-email" name="email" type="email" autoComplete="email" defaultValue={from.email ?? ""} required {...form.fieldProps("email")} />
        <Field label="Password" id="login-password" name="password" type="password" autoComplete="current-password" required {...form.fieldProps("password")} />
        <Button type="submit" disabled={busy}>
          Log in
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => void google()}>
          Continue with Google
        </Button>
        <p>
          <Link to={withNext("/forgot-password", search)} className={LINK}>
            Forgot your password?
          </Link>
        </p>
        {showSignup && <p>
          New here?{" "}
          <Link to={withNext("/signup", search)} className={LINK}>
            Create an account
          </Link>
        </p>}
      </form>
    </>
  );
}
