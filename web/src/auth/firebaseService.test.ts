import { beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = { reload: vi.fn(), getIdToken: vi.fn(), emailVerified: true, uid: "u", email: "a@b.co" };
const auth = { currentUser: currentUser as unknown | null, authStateReady: () => Promise.resolve() };
const m = {
  applyActionCode: vi.fn(),
  checkActionCode: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  reload: vi.fn(),
  getRedirectResult: vi.fn(),
  createUser: vi.fn(),
  sendEmailVerification: vi.fn(),
  signOut: vi.fn(),
  signIn: vi.fn(),
};

vi.mock("firebase/app", () => ({ initializeApp: () => ({}) }));
vi.mock("firebase/auth", () => ({
  GoogleAuthProvider: class {},
  getAuth: () => auth,
  getRedirectResult: (...a: unknown[]) => m.getRedirectResult(...a),
  onIdTokenChanged: vi.fn(),
  applyActionCode: (...a: unknown[]) => m.applyActionCode(...a),
  checkActionCode: (...a: unknown[]) => m.checkActionCode(...a),
  verifyPasswordResetCode: (...a: unknown[]) => m.verifyPasswordResetCode(...a),
  confirmPasswordReset: (...a: unknown[]) => m.confirmPasswordReset(...a),
  reload: (...a: unknown[]) => m.reload(...a),
  createUserWithEmailAndPassword: (...a: unknown[]) => m.createUser(...a),
  sendEmailVerification: (...a: unknown[]) => m.sendEmailVerification(...a),
  sendPasswordResetEmail: vi.fn(),
  signInWithEmailAndPassword: (...a: unknown[]) => m.signIn(...a),
  signInWithPopup: vi.fn(),
  signInWithRedirect: vi.fn(),
  signOut: (...a: unknown[]) => m.signOut(...a),
}));

import { createFirebaseAuthService } from "./firebaseService";

const make = () => createFirebaseAuthService({ apiKey: "AIzaSy", authDomain: "d", projectId: "p", appId: "a" });

beforeEach(() => {
  vi.resetAllMocks();
  auth.currentUser = currentUser;
  currentUser.getIdToken.mockResolvedValue("t");
  m.getRedirectResult.mockResolvedValue(null);
});

describe("firebase action-code methods", () => {
  it("applyEmailVerification applies the code, then reloads and force-refreshes the signed-in user", async () => {
    await make().applyEmailVerification("oob");
    expect(m.applyActionCode).toHaveBeenCalledWith(auth, "oob");
    expect(m.reload).toHaveBeenCalledWith(currentUser);
    expect(currentUser.getIdToken).toHaveBeenCalledWith(true);
  });
  it("applyEmailVerification with nobody signed in only applies the code", async () => {
    auth.currentUser = null;
    await make().applyEmailVerification("oob");
    expect(m.applyActionCode).toHaveBeenCalledOnce();
    expect(m.reload).not.toHaveBeenCalled();
  });
  it("propagates Firebase errors (auth/invalid-action-code)", async () => {
    m.applyActionCode.mockRejectedValue({ code: "auth/invalid-action-code" });
    await expect(make().applyEmailVerification("oob")).rejects.toMatchObject({ code: "auth/invalid-action-code" });
  });
  it("verifyPasswordResetCode returns the email; confirmPasswordReset passes code and password", async () => {
    m.verifyPasswordResetCode.mockResolvedValue("a@b.co");
    const s = make();
    expect(await s.verifyPasswordResetCode("oob")).toBe("a@b.co");
    await s.confirmPasswordReset("oob", "newpassword1");
    expect(m.confirmPasswordReset).toHaveBeenCalledWith(auth, "oob", "newpassword1");
  });
});

describe("firebase email-change action codes", () => {
  it("checkEmailChangeCode returns email and previousEmail without applying", async () => {
    m.checkActionCode.mockResolvedValue({ operation: "VERIFY_AND_CHANGE_EMAIL", data: { email: "new@b.co", previousEmail: "a@b.co" } });
    const info = await make().checkEmailChangeCode("oob", "verifyAndChangeEmail");
    expect(info).toEqual({ email: "new@b.co", previousEmail: "a@b.co" });
    expect(m.checkActionCode).toHaveBeenCalledWith(auth, "oob");
    expect(m.applyActionCode).not.toHaveBeenCalled();
  });
  it("checkEmailChangeCode rejects a code of a different operation as invalid", async () => {
    m.checkActionCode.mockResolvedValue({ operation: "RECOVER_EMAIL", data: { email: "a@b.co", previousEmail: "new@b.co" } });
    await expect(make().checkEmailChangeCode("oob", "verifyAndChangeEmail")).rejects.toMatchObject({ code: "auth/invalid-action-code" });
  });
  it("checkEmailChangeCode propagates Firebase errors", async () => {
    m.checkActionCode.mockRejectedValue({ code: "auth/expired-action-code" });
    await expect(make().checkEmailChangeCode("oob", "recoverEmail")).rejects.toMatchObject({ code: "auth/expired-action-code" });
  });
  it("applyEmailChange applies, then reloads and refreshes the user: signedIn true", async () => {
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: true });
    expect(m.applyActionCode).toHaveBeenCalledWith(auth, "oob");
    expect(m.reload).toHaveBeenCalledWith(currentUser);
    expect(currentUser.getIdToken).toHaveBeenCalledWith(true);
  });
  it("applyEmailChange reports signedIn false when the token was revoked by the change", async () => {
    m.reload.mockRejectedValue({ code: "auth/user-token-expired" });
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: false });
    expect(m.applyActionCode).toHaveBeenCalledOnce();
  });
  it("applyEmailChange signs out when the session cannot be refreshed (FX34)", async () => {
    m.reload.mockRejectedValue({ code: "auth/user-token-expired" });
    await make().applyEmailChange("oob");
    expect(m.signOut).toHaveBeenCalledWith(auth);
  });
  it("applyEmailChange does not claim signedIn for a different account than the code's (FX34)", async () => {
    m.checkActionCode.mockResolvedValue({ operation: "VERIFY_AND_CHANGE_EMAIL", data: { email: "new@x.co", previousEmail: "other@x.co" } });
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: false });
    expect(m.applyActionCode).toHaveBeenCalledOnce();
    expect(m.reload).not.toHaveBeenCalled();
  });
  it("applyEmailChange stays signedIn when the current user matches the code's account (FX34)", async () => {
    m.checkActionCode.mockResolvedValue({ operation: "VERIFY_AND_CHANGE_EMAIL", data: { email: "new@b.co", previousEmail: "A@b.co" } });
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: true });
  });
  it("applyEmailChange with nobody signed in is signedIn false", async () => {
    auth.currentUser = null;
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: false });
  });
  it("applyEmailChange propagates apply errors", async () => {
    m.applyActionCode.mockRejectedValue({ code: "auth/invalid-action-code" });
    await expect(make().applyEmailChange("oob")).rejects.toMatchObject({ code: "auth/invalid-action-code" });
  });
});

describe("firebase signUp", () => {
  it("still resolves when the verification email cannot be sent (VerifyEmail has Resend)", async () => {
    m.createUser.mockResolvedValue({ user: currentUser });
    m.sendEmailVerification.mockRejectedValue({ code: "auth/too-many-requests" });
    await expect(make().signUp("a@b.co", "password1")).resolves.toBeUndefined();
    expect(m.sendEmailVerification).toHaveBeenCalledOnce();
  });
  it("sends the verification email exactly once, only at sign-up", async () => {
    m.createUser.mockResolvedValue({ user: currentUser });
    await make().signUp("a@b.co", "password1");
    expect(m.sendEmailVerification).toHaveBeenCalledOnce();
    expect(m.signIn).not.toHaveBeenCalled();
  });
  it("existing email + right password signs in instead, without sending another verification email", async () => {
    m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
    m.signIn.mockResolvedValue({ user: currentUser });
    await expect(make().signUp("a@b.co", "password1")).resolves.toBeUndefined();
    expect(m.signIn).toHaveBeenCalledWith(auth, "a@b.co", "password1");
    expect(m.sendEmailVerification).not.toHaveBeenCalled();
  });
  it("existing email + wrong password still reports email-already-in-use", async () => {
    m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
    m.signIn.mockRejectedValue({ code: "auth/invalid-credential" });
    await expect(make().signUp("a@b.co", "password1")).rejects.toMatchObject({ code: "auth/email-already-in-use" });
  });
  it("other create failures are not retried as sign-in", async () => {
    m.createUser.mockRejectedValue({ code: "auth/weak-password" });
    await expect(make().signUp("a@b.co", "password1")).rejects.toMatchObject({ code: "auth/weak-password" });
    expect(m.signIn).not.toHaveBeenCalled();
  });
});

describe("firebase redirect sign-in result", () => {
  it("reports the failure code once instead of swallowing it", async () => {
    m.getRedirectResult.mockRejectedValue({ code: "auth/account-exists-with-different-credential" });
    const svc = make();
    expect(await svc.consumeRedirectError()).toBe("auth/account-exists-with-different-credential");
    expect(await svc.consumeRedirectError()).toBeUndefined();
  });
  it("reports nothing when there was no redirect or it succeeded", async () => {
    expect(await make().consumeRedirectError()).toBeUndefined();
  });
});
