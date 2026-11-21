import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { useAuth } from "../AuthProvider";
import { readNext } from "../next";
import { useSignOut } from "../useSignOut";
import { ErrorSummary } from "./parts";
import { useFormError } from "./useFormError";

export const RESEND_COOLDOWN_SECONDS = 60;

const cooldownKey = (email: string | null | undefined) => `iaudit.verifyResendUntil:${email ?? ""}`;

/** Seconds left on a persisted resend cooldown (it must survive a reload). */
function storedCooldown(email: string | null | undefined): number {
  try {
    const until = Number(sessionStorage.getItem(cooldownKey(email)));
    return Math.max(0, Math.ceil((until - Date.now()) / 1000));
  } catch {
    return 0;
  }
}

export function VerifyEmail() {
  const { service, user } = useAuth();
  const { search } = useLocation();
  const next = readNext(search);
  const { signOut, error: signOutError } = useSignOut();
  const [cooldown, setCooldown] = useState(() => storedCooldown(user?.email));
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checkingNow, setCheckingNow] = useState(false);
  const form = useFormError();
  const checking = useRef(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  // Reload + forced token refresh; on success the guard redirects (user.emailVerified flips).
  const check = useCallback(
    async (announce: boolean) => {
      if (checking.current) return;
      checking.current = true;
      if (announce) {
        setNote(null);
        setCheckingNow(true);
      }
      try {
        const fresh = await service.refreshUser();
        if (fresh && !fresh.emailVerified && announce) {
          setNote("We haven't seen your verification yet. Open the link in the email, then try again.");
        }
      } catch {
        if (announce) setNote("Couldn't check just now. Please try again.");
      } finally {
        checking.current = false;
        setCheckingNow(false);
      }
    },
    [service],
  );

  useEffect(() => {
    const onFocus = () => void check(false);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [check]);

  async function resend() {
    form.clear();
    setNote(null);
    setBusy(true);
    try {
      await service.sendVerificationEmail(next);
      setNote("Verification email sent.");
      setCooldown(RESEND_COOLDOWN_SECONDS);
      try {
        sessionStorage.setItem(cooldownKey(user?.email), String(Date.now() + RESEND_COOLDOWN_SECONDS * 1000));
      } catch {
        // Storage blocked: the cooldown just won't survive a reload.
      }
    } catch (err) {
      form.fail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Verify your email</h1>
      <div className="auth-form">
        {form.error && <ErrorSummary error={form.error} search="" />}
        <p>
          Check your inbox — and your spam folder. We sent a verification link to <strong>{user?.email}</strong>.
        </p>
        {note && <p role="status">{note}</p>}
        {signOutError && <p role="alert">{signOutError}</p>}
        <button type="button" className="primary" disabled={checkingNow} onClick={() => void check(true)}>
          {checkingNow ? "Checking…" : "I've verified"}
        </button>
        <button type="button" className="secondary" disabled={busy || cooldown > 0} onClick={() => void resend()}>
          {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}
        </button>
        <p>
          Wrong address?{" "}
          <button type="button" className="secondary" onClick={() => void signOut()}>
            Sign out
          </button>
        </p>
      </div>
    </>
  );
}
