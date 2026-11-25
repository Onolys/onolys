/** Firebase Auth implementation (modular `firebase/auth` only; PRD R2, D8). */
import { initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  applyActionCode,
  checkActionCode,
  confirmPasswordReset as fbConfirmPasswordReset,
  createUserWithEmailAndPassword,
  getAuth,
  getRedirectResult,
  onIdTokenChanged,
  reload,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithRedirect,
  signOut as fbSignOut,
  verifyPasswordResetCode as fbVerifyPasswordResetCode,
  type User,
} from "firebase/auth";
import { createApiClient, DEFAULT_BASE_URL } from "../api/client";
import { AuthError, type AuthService, type AuthUser, type EmailChangeKind } from "./types";

const OPERATION: Record<EmailChangeKind, string> = {
  verifyAndChangeEmail: "VERIFY_AND_CHANGE_EMAIL",
  recoverEmail: "RECOVER_EMAIL",
};

export interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
}

const toUser = (u: User | null): AuthUser | null =>
  u ? { uid: u.uid, email: u.email, displayName: u.displayName, emailVerified: u.emailVerified } : null;

const POPUP_FALLBACK = new Set([
  "auth/popup-blocked",
  "auth/operation-not-supported-in-this-environment",
  "auth/web-storage-unsupported",
]);

const isMobile = () => /Android|iPhone|iPad|iPod/i.test(globalThis.navigator?.userAgent ?? "");

/** Both email routes answer 202 on success; anything else maps to a code `mapAuthError` words (no fallback sender, PRD D3). */
async function emailCall(run: () => Promise<{ response: Response }>): Promise<void> {
  let status: number;
  try {
    status = (await run()).response.status;
  } catch {
    throw new AuthError("email/unavailable");
  }
  if (status === 429) throw new AuthError("email/rate-limited");
  if (status < 200 || status >= 300) throw new AuthError("email/unavailable");
}

type EmailApi = (getToken: () => Promise<string | null>) => Pick<ReturnType<typeof createApiClient>, "POST">;

export interface FirebaseServiceOptions {
  /** Client for the server-sent email routes. Omitted: the same-origin prod `/v1` client. `null`: no email flows (they reject `email/unavailable`). */
  emailApi?: EmailApi | null;
}

export function createFirebaseAuthService(config: FirebaseWebConfig, options: FirebaseServiceOptions = {}): AuthService {
  const app = initializeApp(config);
  const auth = getAuth(app);
  const listeners = new Set<(u: AuthUser | null) => void>();
  const emit = () => {
    const u = toUser(auth.currentUser);
    for (const l of [...listeners]) l(u ? { ...u } : null);
  };

  // Completes a redirect sign-in; the token listener below reports the user.
  let redirectError: Promise<string | undefined> | undefined = getRedirectResult(auth).then(
    () => undefined,
    (err: unknown) => (err as { code?: string } | null)?.code ?? "auth/unknown",
  );
  onIdTokenChanged(auth, emit);

  // Same-origin `/v1` in prod; the verification route takes the user's ID token, the reset route none.
  const defaultEmailApi: EmailApi = (getToken) =>
    createApiClient({
      baseUrl: new URL(import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL, window.location.origin).href.replace(/\/$/, ""),
      getToken,
      onSessionExpired: () => {},
    });
  const emailApi: EmailApi = (getToken) => {
    const make = options.emailApi === undefined ? defaultEmailApi : options.emailApi;
    if (!make) throw new AuthError("email/unavailable");
    return make(getToken);
  };
  const requestVerification = (user: User, next?: string) =>
    emailCall(() => emailApi(() => user.getIdToken()).POST("/auth/email/verification", { body: { next } }));

  const need = (): User => {
    if (!auth.currentUser) throw new AuthError("auth/requires-recent-login");
    return auth.currentUser;
  };

  return {
    onAuthStateChanged(cb) {
      listeners.add(cb);
      // Only report once the SDK has loaded persisted state.
      void auth.authStateReady().then(() => {
        if (listeners.has(cb)) cb(toUser(auth.currentUser));
      });
      return () => void listeners.delete(cb);
    },
    async signUp(email, password, next) {
      let cred;
      try {
        cred = await createUserWithEmailAndPassword(auth, email, password);
      } catch (err) {
        if ((err as { code?: string } | null)?.code !== "auth/email-already-in-use") throw err;
        // Existing account (e.g. unverified, user came back to Sign up): the right password just signs in,
        // and the guards route to the verify page or the app. No new verification email (each send voids earlier links).
        try {
          await signInWithEmailAndPassword(auth, email, password);
        } catch (signInErr) {
          const code = (signInErr as { code?: string } | null)?.code;
          // Wrong password / no such credential: keep the "already exists, log in instead" error.
          // Anything else (rate limit, network, disabled account) is its own problem: surface it.
          if (code === "auth/invalid-credential" || code === "auth/wrong-password" || code === "auth/user-not-found") throw err;
          throw signInErr;
        }
        return;
      }
      try {
        await requestVerification(cred.user, next);
      } catch {
        // The account exists and the user is signed in; the verify page offers Resend and shows its own error.
      }
      emit();
    },
    async consumeRedirectError() {
      const pending = redirectError;
      redirectError = undefined;
      return pending;
    },
    async signIn(email, password) {
      await signInWithEmailAndPassword(auth, email, password);
    },
    async signInWithGoogle() {
      const provider = new GoogleAuthProvider();
      if (isMobile()) return signInWithRedirect(auth, provider);
      try {
        await signInWithPopup(auth, provider);
      } catch (err) {
        const code = (err as { code?: string }).code ?? "";
        if (POPUP_FALLBACK.has(code)) return signInWithRedirect(auth, provider);
        throw err;
      }
    },
    async sendPasswordReset(email) {
      await emailCall(() => emailApi(async () => null).POST("/auth/email/password-reset", { body: { email } }));
    },
    async sendVerificationEmail(next) {
      await requestVerification(need(), next);
    },
    async refreshUser() {
      const user = auth.currentUser;
      if (!user) return null;
      await reload(user);
      await user.getIdToken(true); // the cached token lacks email_verified until refreshed
      emit();
      return toUser(auth.currentUser);
    },
    async applyEmailVerification(oobCode) {
      await applyActionCode(auth, oobCode);
      const user = auth.currentUser;
      if (user) {
        await reload(user);
        await user.getIdToken(true); // the cached token lacks email_verified until refreshed
        emit();
      }
    },
    async checkEmailVerificationCode(oobCode) {
      const info = await checkActionCode(auth, oobCode); // does not consume the code
      const email = info.data.email;
      if (info.operation !== "VERIFY_EMAIL" || !email) throw new AuthError("auth/invalid-action-code");
      return email;
    },
    async verifyPasswordResetCode(oobCode) {
      return fbVerifyPasswordResetCode(auth, oobCode);
    },
    async confirmPasswordReset(oobCode, newPassword) {
      await fbConfirmPasswordReset(auth, oobCode, newPassword);
    },
    async checkEmailChangeCode(oobCode, kind) {
      const info = await checkActionCode(auth, oobCode); // does not consume the code
      const email = info.data.email;
      if (info.operation !== OPERATION[kind] || !email) throw new AuthError("auth/invalid-action-code");
      return { email, previousEmail: info.data.previousEmail ?? null };
    },
    async applyEmailChange(oobCode) {
      // Which account the code belongs to (best effort: applyActionCode below reports invalid codes).
      let info: Awaited<ReturnType<typeof checkActionCode>> | undefined;
      try {
        info = await checkActionCode(auth, oobCode);
      } catch {
        info = undefined;
      }
      const emails = [info?.data?.email, info?.data?.previousEmail].filter(Boolean).map((e) => e!.toLowerCase());
      const before = auth.currentUser;
      await applyActionCode(auth, oobCode);
      const user = auth.currentUser;
      if (!user) return { signedIn: false };
      if (emails.length > 0 && !emails.includes((before?.email ?? "").toLowerCase())) return { signedIn: false }; // someone else's link
      try {
        await reload(user);
        await user.getIdToken(true);
      } catch {
        try {
          await fbSignOut(auth);
        } catch {
          /* already signed out */
        } // the email change revoked this session's tokens: do not rely on the SDK
        return { signedIn: false };
      }
      emit();
      return { signedIn: true };
    },
    async getToken(forceRefresh = false) {
      const user = auth.currentUser;
      return user ? user.getIdToken(forceRefresh) : null;
    },
    async signOut() {
      await fbSignOut(auth);
    },
  };
}
