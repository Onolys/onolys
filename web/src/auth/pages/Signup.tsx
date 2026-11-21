import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import { useAuth } from "../AuthProvider";
import { EMAIL_PATTERN, MIN_PASSWORD_LENGTH } from "../errors";
import { withNext } from "../next";
import { ErrorSummary } from "./parts";
import { useFormError } from "./useFormError";

export function Signup() {
  const { service } = useAuth();
  const { search } = useLocation();
  const [busy, setBusy] = useState(false);
  const form = useFormError();

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    if (!email) return form.failWith("Enter your email.", "email");
    if (!EMAIL_PATTERN.test(email)) return form.failWith("Enter a valid email address.", "email");
    if (password.length < MIN_PASSWORD_LENGTH) {
      return form.failWith(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`, "password");
    }
    form.clear();
    setBusy(true);
    try {
      await service.signUp(email, password); // the guard then moves us to /verify-email
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
      <h1>Sign up</h1>
      <form className="auth-form" onSubmit={(e) => void onSubmit(e)} noValidate>
        {form.error && <ErrorSummary error={form.error} search={search} />}
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required {...form.fieldProps("email")} />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH} {...form.fieldProps("password")} />
        </label>
        <p className="form-note">At least {MIN_PASSWORD_LENGTH} characters. No other rules.</p>
        <button type="submit" className="primary" disabled={busy}>
          Create account
        </button>
        <button type="button" className="secondary" onClick={() => void google()}>
          Continue with Google
        </button>
        <p>
          Already have an account? <Link to={withNext("/login", search)}>Log in</Link>
        </p>
      </form>
    </>
  );
}
