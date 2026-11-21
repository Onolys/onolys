import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useAuth } from "../AuthProvider";
import { MIN_PASSWORD_LENGTH, errorCode, mapAuthError } from "../errors";
import type { EmailChangeInfo, EmailChangeKind } from "../types";
import { ErrorSummary } from "./parts";
import type { LoginState } from "./Login";
import { useFormError } from "./useFormError";

/**
 * In-app handler for Firebase email links (verify email, reset password, change of email, recover email). Firebase's hosted handler
 * fails for this project (the link carries a non-web API key), so the email action URL points here
 * and the page uses our own auth instance. The `apiKey` query param is ignored.
 */

/**
 * Hosts (besides this origin) a continue link may send the user back to: the Firebase auth domain plus any
 * comma-separated hostnames in `VITE_APP_HOSTS` (e.g. a sibling environment that shares the auth project).
 */
export function appHosts(env: Record<string, string | undefined> = import.meta.env): Set<string> {
  const list = [env.VITE_FIREBASE_AUTH_DOMAIN, ...(env.VITE_APP_HOSTS ?? "").split(",")];
  return new Set(list.map((h) => (h ?? "").trim().toLowerCase()).filter(Boolean));
}

export type Continue = { kind: "path"; path: string } | { kind: "external"; href: string };

/** Never an open redirect: same-origin path, or an https URL on a configured app host, else `/`. */
export function resolveContinue(raw: string | null, origin: string = window.location.origin, hosts: Set<string> = appHosts()): Continue {
  const home: Continue = { kind: "path", path: "/" };
  if (!raw) return home;
  let url: URL;
  try {
    url = new URL(raw, origin);
  } catch {
    return home;
  }
  if (url.origin === origin) return { kind: "path", path: url.pathname + url.search + url.hash };
  if (url.protocol === "https:" && !url.username && !url.password && hosts.has(url.hostname)) {
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
  if (oobCode && (mode === "verifyAndChangeEmail" || mode === "recoverEmail")) {
    return <EmailChangeAction key={mode} mode={mode} oobCode={oobCode} continueUrl={continueUrl} />;
  }
  return (
    <>
      <h1>This link isn't valid</h1>
      <p>The link is incomplete or not one we recognise. Request a new one and try again.</p>
      {mode === "revertSecondFactorAddition" && <p>Two-step verification isn't used on Onolys, so there is nothing to undo.</p>}
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

  if (user?.emailVerified && !done) {
    return (
      <>
        <h1>Already verified</h1>
        <p role="status">Your email address is already verified.</p>
        <button type="button" className="primary" onClick={carryOn}>
          Continue
        </button>
      </>
    );
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

/** The pre-check failed for a reason other than an invalid/expired code (network, throttling): the link may still be fine. */
function CheckFailed({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <>
      <h1>Couldn't check your link</h1>
      <p role="alert">{message}</p>
      <button type="button" className="primary" onClick={onRetry}>
        Try again
      </button>
    </>
  );
}

function ResetPasswordAction({ oobCode }: { oobCode: string }) {
  const { service } = useAuth();
  const [email, setEmail] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const form = useFormError();

  // Checking the code does not consume it, so this is safe on load.
  useEffect(() => {
    let live = true;
    service.verifyPasswordResetCode(oobCode).then(
      (e) => live && setEmail(e),
      (err) => {
        if (!live) return;
        if (EXPIRED.has(errorCode(err) ?? "")) setInvalid(true);
        else setCheckError(mapAuthError(errorCode(err)).message);
      },
    );
    return () => {
      live = false;
    };
  }, [service, oobCode, attempt]);

  function retryCheck() {
    setCheckError(null);
    setAttempt((n) => n + 1);
  }

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
      // Login shows "Password updated" and prefills the email.
      void navigate("/login", { replace: true, state: { email: email ?? undefined, passwordUpdated: true } satisfies LoginState });
    } catch (err) {
      if (EXPIRED.has(errorCode(err) ?? "")) setInvalid(true);
      else form.fail(err);
    } finally {
      setBusy(false);
    }
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
  if (checkError) return <CheckFailed message={checkError} onRetry={retryCheck} />;
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

const COPY: Record<EmailChangeKind, { title: string; button: string; doneTitle: string }> = {
  verifyAndChangeEmail: { title: "Confirm your new email", button: "Confirm new email", doneTitle: "Email updated" },
  recoverEmail: { title: "Restore your email", button: "Restore this email", doneTitle: "Email restored" },
};

function EmailChangeAction({ mode, oobCode, continueUrl }: { mode: EmailChangeKind; oobCode: string; continueUrl: string | null }) {
  const { service } = useAuth();
  const navigate = useNavigate();
  const [info, setInfo] = useState<EmailChangeInfo | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [signedIn, setSignedIn] = useState<boolean | null>(null); // null until applied
  const [resetSent, setResetSent] = useState(false);
  const form = useFormError();
  const next = resolveContinue(continueUrl);
  const copy = COPY[mode];

  // Checking the code does not consume it, so this is safe on load. Applying waits for a click.
  useEffect(() => {
    let live = true;
    service.checkEmailChangeCode(oobCode, mode).then(
      (i) => live && setInfo(i),
      (err) => {
        if (!live) return;
        if (EXPIRED.has(errorCode(err) ?? "")) setInvalid(true);
        else setCheckError(mapAuthError(errorCode(err)).message);
      },
    );
    return () => {
      live = false;
    };
  }, [service, oobCode, mode, attempt]);

  function retryCheck() {
    setCheckError(null);
    setAttempt((n) => n + 1);
  }

  async function apply() {
    form.clear();
    setBusy(true);
    try {
      const result = await service.applyEmailChange(oobCode);
      setSignedIn(result.signedIn);
    } catch (err) {
      if (EXPIRED.has(errorCode(err) ?? "")) setInvalid(true);
      else form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (!info) return;
    form.clear();
    try {
      await service.sendPasswordReset(info.email);
      setResetSent(true);
    } catch (err) {
      form.fail(err);
    }
  }

  function carryOn() {
    if (next.kind === "external") window.location.assign(next.href);
    else void navigate(next.path);
  }

  if (invalid) {
    return (
      <>
        <h1>Link expired</h1>
        <p role="alert">This link is invalid, has expired, or was already used.</p>
        <p>
          <Link to="/login">Go to log in</Link>
        </p>
      </>
    );
  }
  if (checkError) return <CheckFailed message={checkError} onRetry={retryCheck} />;
  if (!info) return <h1>Checking your link…</h1>;

  if (signedIn !== null) {
    return (
      <>
        <h1>{copy.doneTitle}</h1>
        {mode === "verifyAndChangeEmail" ? (
          <p role="status">
            Your email address is now <strong>{info.email}</strong>.
            {signedIn ? "" : " Log in again with your new email."}
          </p>
        ) : (
          <>
            <p role="status">
              Your email address is back to <strong>{info.email}</strong>.
            </p>
            <p>If you didn't make this change, someone else may have access to your account. Reset your password to be safe.</p>
            {form.error && <ErrorSummary error={form.error} search="" />}
            {resetSent ? (
              <p role="status">Password reset email sent. Check your inbox.</p>
            ) : (
              <button type="button" className="primary" onClick={() => void resetPassword()}>
                Reset my password
              </button>
            )}
          </>
        )}
        {signedIn ? (
          <button type="button" className="primary" onClick={carryOn}>
            Continue
          </button>
        ) : (
          <p>
            <Link to="/login">Log in</Link>
          </p>
        )}
      </>
    );
  }

  return (
    <>
      <h1>{copy.title}</h1>
      <div className="auth-form">
        {form.error && <ErrorSummary error={form.error} search="" />}
        {mode === "verifyAndChangeEmail" ? (
          <p>
            Change the email address on your account to <strong>{info.email}</strong>.
          </p>
        ) : (
          <p>
            Restore the email address on your account to <strong>{info.email}</strong>
            {info.previousEmail ? <> (currently {info.previousEmail})</> : null}.
          </p>
        )}
        <button type="button" className="primary" disabled={busy} onClick={() => void apply()}>
          {copy.button}
        </button>
      </div>
    </>
  );
}
