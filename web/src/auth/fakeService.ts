/**
 * In-memory AuthService for mock mode and tests (`VITE_AUTH_MODE=fake`).
 * Tokens match SP04 `AUTH_MODE=fake` (`Bearer test:<uid>`). No persistence.
 */
import { fakeToken } from "./fake";
import { AuthError, type AuthService, type AuthUser, type EmailChangeKind } from "./types";

type CodeKind = "verifyEmail" | "resetPassword" | EmailChangeKind;

interface Account {
  uid: string;
  email: string;
  password: string | null;
  verified: boolean;
}

export interface FakeAuthOptions {
  /** Mock dev mode: refreshUser() marks the account verified (no inbox to click in). */
  autoVerify?: boolean;
}

export interface FakeAuthService extends AuthService {
  calls: {
    signUps: number;
    signIns: number;
    googleSignIns: number;
    verificationEmails: number;
    /** `next` each verification email asked to come back to (default "/"). */
    verificationNexts: string[];
    forcedRefreshes: number;
    resets: string[];
    emailVerifications: number;
    passwordResets: number;
    emailChanges: number;
  };
  /**
   * Test shortcut: mint a one-time email action code for an existing account (`email` = its current address).
   * verifyAndChangeEmail takes `newEmail`; recoverEmail takes `previousEmail` (the address to restore).
   */
  issueActionCode(
    kind: CodeKind,
    email: string,
    opts?: { expired?: boolean; newEmail?: string; previousEmail?: string },
  ): string;
  /** Pretend the user clicked the email link (visible after the next refreshUser). */
  markVerified(email: string): void;
  /** Test shortcut: be signed in as this account right now. */
  signedInAs(email: string, opts: { verified: boolean }): void;
}

const uidFor = (email: string) => `u_${email.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;
const norm = (email: string) => email.trim().toLowerCase();

export function createFakeAuthService(options: FakeAuthOptions = {}): FakeAuthService {
  const accounts = new Map<string, Account>();
  const listeners = new Set<(u: AuthUser | null) => void>();
  let currentEmail: string | null = null;
  // Verification state the app has seen (the "cached token"); the account holds the truth.
  let seenVerified = false;

  const view = (): AuthUser | null => {
    if (!currentEmail) return null;
    const a = accounts.get(currentEmail)!;
    return { uid: a.uid, email: a.email, emailVerified: seenVerified };
  };
  const emit = () => {
    const u = view();
    for (const l of [...listeners]) l(u ? { ...u } : null);
  };
  const enter = (email: string) => {
    currentEmail = email;
    seenVerified = accounts.get(email)!.verified;
    emit();
  };

  const calls: FakeAuthService["calls"] = {
    signUps: 0,
    signIns: 0,
    googleSignIns: 0,
    verificationEmails: 0,
    verificationNexts: [],
    forcedRefreshes: 0,
    resets: [],
    emailVerifications: 0,
    passwordResets: 0,
    emailChanges: 0,
  };
  const codes = new Map<string, { kind: CodeKind; email: string; expired: boolean; target?: string }>();
  let codeSeq = 0;
  const takeCode = (code: string, kind: CodeKind, consume: boolean) => {
    const c = codes.get(code);
    if (!c || c.kind !== kind) throw new AuthError("auth/invalid-action-code");
    if (c.expired) throw new AuthError("auth/expired-action-code");
    if (consume) codes.delete(code);
    return c;
  };

  return {
    calls,
    onAuthStateChanged(cb) {
      listeners.add(cb);
      void Promise.resolve().then(() => {
        if (listeners.has(cb)) {
          const u = view();
          cb(u ? { ...u } : null);
        }
      });
      return () => void listeners.delete(cb);
    },
    async signUp(email, password, next = "/") {
      calls.signUps++;
      const key = norm(email);
      const existing = accounts.get(key);
      if (existing) {
        // Like the Firebase service: the right password signs in (no new verification email).
        if (existing.password === password) return enter(key);
        throw new AuthError("auth/email-already-in-use");
      }
      if (password.length < 6) throw new AuthError("auth/weak-password");
      accounts.set(key, { uid: uidFor(key), email: key, password, verified: false });
      calls.verificationEmails++;
      calls.verificationNexts.push(next);
      enter(key);
    },
    async signIn(email, password) {
      calls.signIns++;
      const a = accounts.get(norm(email));
      if (!a || a.password !== password) throw new AuthError("auth/invalid-credential");
      enter(a.email);
    },
    async signInWithGoogle() {
      calls.googleSignIns++;
      const key = "google.user@example.com";
      if (!accounts.has(key)) accounts.set(key, { uid: uidFor(key), email: key, password: null, verified: true });
      enter(key);
    },
    async consumeRedirectError() {
      return undefined;
    },
    async sendPasswordReset(email) {
      calls.resets.push(email);
      if (!accounts.has(norm(email))) throw new AuthError("auth/user-not-found");
    },
    async sendVerificationEmail(next = "/") {
      if (!currentEmail) throw new AuthError("auth/requires-recent-login");
      calls.verificationEmails++;
      calls.verificationNexts.push(next);
    },
    async refreshUser() {
      if (!currentEmail) return null;
      calls.forcedRefreshes++;
      const a = accounts.get(currentEmail)!;
      if (options.autoVerify) a.verified = true;
      seenVerified = a.verified;
      emit();
      return view();
    },
    async applyEmailVerification(oobCode) {
      const c = takeCode(oobCode, "verifyEmail", true);
      calls.emailVerifications++;
      const a = accounts.get(c.email);
      if (a) a.verified = true;
      if (currentEmail && a) {
        calls.forcedRefreshes++;
        seenVerified = accounts.get(currentEmail)!.verified;
        emit();
      }
    },
    async verifyPasswordResetCode(oobCode) {
      return takeCode(oobCode, "resetPassword", false).email;
    },
    async confirmPasswordReset(oobCode, newPassword) {
      const c = takeCode(oobCode, "resetPassword", false);
      if (newPassword.length < 6) throw new AuthError("auth/weak-password");
      takeCode(oobCode, "resetPassword", true);
      calls.passwordResets++;
      const a = accounts.get(c.email);
      if (a) a.password = newPassword;
    },
    async checkEmailChangeCode(oobCode, kind) {
      const c = takeCode(oobCode, kind, false);
      const target = c.target ?? c.email;
      return { email: target, previousEmail: c.email };
    },
    async applyEmailChange(oobCode) {
      const c = codes.get(oobCode);
      if (!c || (c.kind !== "verifyAndChangeEmail" && c.kind !== "recoverEmail")) throw new AuthError("auth/invalid-action-code");
      takeCode(oobCode, c.kind, true);
      const target = c.target ?? c.email;
      const a = accounts.get(c.email);
      if (!a) throw new AuthError("auth/invalid-action-code");
      if (target !== c.email && accounts.has(target)) throw new AuthError("auth/email-already-in-use");
      calls.emailChanges++;
      accounts.delete(c.email);
      accounts.set(target, { ...a, email: target });
      // Changing the email revokes the account's tokens: whoever was signed in is signed out.
      if (currentEmail === c.email) {
        currentEmail = null;
        seenVerified = false;
        emit();
      }
      return { signedIn: false };
    },
    issueActionCode(kind, email, opts = {}) {
      const code = `code_${++codeSeq}`;
      const target = kind === "verifyAndChangeEmail" ? opts.newEmail : kind === "recoverEmail" ? opts.previousEmail : undefined;
      codes.set(code, { kind, email: norm(email), expired: Boolean(opts.expired), target: target ? norm(target) : undefined });
      return code;
    },
    async getToken(forceRefresh) {
      if (!currentEmail) return null;
      if (forceRefresh) calls.forcedRefreshes++;
      return fakeToken(accounts.get(currentEmail)!.uid);
    },
    async signOut() {
      currentEmail = null;
      seenVerified = false;
      emit();
    },
    markVerified(email) {
      const a = accounts.get(norm(email));
      if (a) a.verified = true;
    },
    signedInAs(email, { verified }) {
      const key = norm(email);
      accounts.set(key, { uid: uidFor(key), email: key, password: "password1", verified });
      enter(key);
    },
  };
}
