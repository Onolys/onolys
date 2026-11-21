import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useAuth } from "../AuthProvider";
import { MIN_PASSWORD_LENGTH, errorCode } from "../errors";
import { ErrorSummary } from "./parts";
import { useFormError } from "./useFormError";

/**
 * In-app handler for Firebase email links (verify email, reset password). Firebase's hosted handler
 * fails for this project (the link carries a non-web API key), so the email action URL points here
 * and the page uses our own auth instance. The `apiKey` query param is ignored.
 */

/** Hosts a continue link may send the user back to: this origin plus the app's own sites (staging shares the auth project). */
const APP_HOSTS = new Set(["app.onolys.com", "onolys-app.web.app", "onolys-app-staging.web.app"]);

export type Continue = { kind: "path"; path: string } | { kind: "external"; href: string };

/** Never an open redirect: same-origin path, or an https URL on a known app host, else `/`. */
export function resolveContinue(raw: string | null, origin: string = window.location.origin): Continue {
  const home: Continue = { kind: "path", path: "/" };
  if (!raw) return home;
  let url: URL;
  try {
    url = new URL(raw, origin);
  } catch {
    return home;
  }
  if (url.origin === origin) return { kind: "path", path: url.pathname + url.search + url.hash };
  if (url.protocol === "https:" && !url.username && !url.password && APP_HOSTS.has(url.hostname)) {
    return { kind: "external", href: url.href };
  }
  return home;
}

const EXPIRED = new Set(["auth/invalid-action-code", "auth/expired-action-code"]);

export function AuthAction() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const mode = params.get("mode");
  const oobCode = params.get("oobCode");
  const continueUrl = params.get("continueUrl");

  if (oobCode && mode === "verifyEmail") return <VerifyEmailAction oobCode={oobCode} continueUrl={continueUrl} />;
  if (oobCode && mode === "resetPassword") return <ResetPasswordAction oobCode={oobCode} />;
  return (
    <>
      <h1>This link isn't valid</h1>
      <p>The link is incomplete or not one we recognise. Request a new one and try again.</p>
      <p>
        <Link to="/login">Go to log in</Link>
      </p>
    </>
  );
}

function VerifyEmailAction({ oobCode, continueUrl }: { oobCode: string; continueUrl: string | null }) {
  const { service, user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const form = useFormError();
  const next = resolveContinue(continueUrl);

  // Applied only on click: mail scanners prefetch links and would burn the one-time code.
  async function verify() {
    form.clear();
    setFailure(null);
    setBusy(true);
    try {
      await service.applyEmailVerification(oobCode);
      setDone(true);
    } catch (err) {
      const code = errorCode(err) ?? "";
      if (EXPIRED.has(code)) setFailure(code);
      else form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  function carryOn() {
    if (next.kind === "external") window.location.assign(next.href);
    else void navigate(next.path);
  }

  if (done) {
    return (
      <>
        <h1>Email verified</h1>
        <p role="status">Your email address is verified.</p>
        <button type="button" className="primary" onClick={carryOn}>
          Continue
        </button>
      </>
    );
  }

  return (
    <>
      <h1>Verify your email</h1>
      <div className="auth-form">
        {form.error && <ErrorSummary error={form.error} search="" />}
        {failure && (
          <div role="alert" className="form-error">
            <p>This verification link is invalid, has expired, or was already used.</p>
            <p>
              <Link to={user ? "/verify-email" : "/login"}>
                {user ? "Get a new verification email" : "Log in to get a new verification email"}
              </Link>
            </p>
          </div>
        )}
        <p>Confirm your email address to finish setting up your account.</p>
        <button type="button" className="primary" disabled={busy} onClick={() => void verify()}>
          Verify my email
        </button>
      </div>
    </>
  );
}

function ResetPasswordAction({ oobCode }: { oobCode: string }) {
  const { service } = useAuth();
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const form = useFormError();

  // Checking the code does not consume it, so this is safe on load.
  useEffect(() => {
    let live = true;
    service.verifyPasswordResetCode(oobCode).then(
      (e) => live && setEmail(e),
      () => live && setInvalid(true),
    );
    return () => {
      live = false;
    };
  }, [service, oobCode]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password") ?? "");
    if (password.length < MIN_PASSWORD_LENGTH) {
      form.failWith(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }
    form.clear();
    setBusy(true);
    try {
      await service.confirmPasswordReset(oobCode, password);
      setDone(true);
    } catch (err) {
      if (EXPIRED.has(errorCode(err) ?? "")) setInvalid(true);
      else form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <>
        <h1>Password updated</h1>
        <p role="status">Your password has been changed.</p>
        <p>
          <Link to="/login">Log in</Link>
        </p>
      </>
    );
  }
  if (invalid) {
    return (
      <>
        <h1>Reset link expired</h1>
        <p role="alert">This reset link is invalid, has expired, or was already used.</p>
        <p>
          <Link to="/forgot-password">Request a new reset link</Link>
        </p>
      </>
    );
  }
  if (!email) return <h1>Checking your link…</h1>;

  return (
    <>
      <h1>Choose a new password</h1>
      <form className="auth-form" onSubmit={(e) => void onSubmit(e)} noValidate>
        {form.error && <ErrorSummary error={form.error} search="" />}
        <p>
          Resetting the password for <strong>{email}</strong>.
        </p>
        <label>
          New password
          <input name="password" type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH} />
        </label>
        <p className="form-note">At least {MIN_PASSWORD_LENGTH} characters. No other rules.</p>
        <button type="submit" className="primary" disabled={busy}>
          Update password
        </button>
      </form>
    </>
  );
}
