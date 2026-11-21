import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../AuthProvider";
import { EMAIL_PATTERN } from "../errors";
import { withNext } from "../next";
import { ErrorSummary } from "./parts";
import { useFormError } from "./useFormError";

export function Login() {
  const { service } = useAuth();
  const { search } = useLocation();
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
    form.clear();
    try {
      await service.signInWithGoogle();
    } catch (err) {
      form.fail(err);
    }
  }

  return (
    <>
      <h1>Log in</h1>
      <form className="auth-form" onSubmit={(e) => void onSubmit(e)} noValidate>
        {form.error && <ErrorSummary error={form.error} search={search} />}
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required {...form.fieldProps("email")} />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete="current-password" required {...form.fieldProps("password")} />
        </label>
        <button type="submit" className="primary" disabled={busy}>
          Log in
        </button>
        <button type="button" className="secondary" onClick={() => void google()}>
          Continue with Google
        </button>
        <p>
          <Link to={withNext("/forgot-password", search)}>Forgot your password?</Link>
        </p>
        <p>
          New here? <Link to={withNext("/signup", search)}>Create an account</Link>
        </p>
      </form>
    </>
  );
}
