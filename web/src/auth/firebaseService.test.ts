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
  signInWithEmailAndPassword: (...a: unknown[]) => m.signIn(...a),
  signInWithPopup: vi.fn(),
  signInWithRedirect: vi.fn(),
  signOut: (...a: unknown[]) => m.signOut(...a),
}));

import { createFirebaseAuthService } from "./firebaseService";

const make = () => createFirebaseAuthService({ apiKey: "AIzaSy", authDomain: "d", projectId: "p", appId: "a" });

const fetchMock = vi.fn();
const sent = () => {
  const req = fetchMock.mock.calls.at(-1)![0] as Request;
  return req;
};
const reply = (status: number, body: unknown = {}) =>
  fetchMock.mockImplementation(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  reply(202);
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
  it("applyEmailChange signs out when the session cannot be refreshed", async () => {
    m.reload.mockRejectedValue({ code: "auth/user-token-expired" });
    await make().applyEmailChange("oob");
    expect(m.signOut).toHaveBeenCalledWith(auth);
  });
  it("applyEmailChange does not claim signedIn for a different account than the code's", async () => {
    m.checkActionCode.mockResolvedValue({ operation: "VERIFY_AND_CHANGE_EMAIL", data: { email: "new@x.co", previousEmail: "other@x.co" } });
    expect(await make().applyEmailChange("oob")).toEqual({ signedIn: false });
    expect(m.applyActionCode).toHaveBeenCalledOnce();
    expect(m.reload).not.toHaveBeenCalled();
  });
  it("applyEmailChange stays signedIn when the current user matches the code's account", async () => {
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
    reply(503, { error: { code: "email_unavailable" } });
    await expect(make().signUp("a@b.co", "password1")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledOnce();
  });
  it("still resolves when the network is down", async () => {
    m.createUser.mockResolvedValue({ user: currentUser });
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(make().signUp("a@b.co", "password1")).resolves.toBeUndefined();
  });
  it("sends the verification email exactly once, only at sign-up, via the API with the ID token", async () => {
    m.createUser.mockResolvedValue({ user: currentUser });
    await make().signUp("a@b.co", "password1", "/settings");
    expect(fetchMock).toHaveBeenCalledOnce();
    const req = sent();
    expect(new URL(req.url).pathname).toBe("/v1/auth/email/verification");
    expect(req.headers.get("authorization")).toBe("Bearer t");
    expect(await req.json()).toEqual({ next: "/settings" });
    expect(m.signIn).not.toHaveBeenCalled();
  });
  it("existing email + right password signs in instead, without sending another verification email", async () => {
    m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
    m.signIn.mockResolvedValue({ user: currentUser });
    await expect(make().signUp("a@b.co", "password1")).resolves.toBeUndefined();
    expect(m.signIn).toHaveBeenCalledWith(auth, "a@b.co", "password1");
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("existing email + wrong password still reports email-already-in-use", async () => {
    m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
    m.signIn.mockRejectedValue({ code: "auth/invalid-credential" });
    await expect(make().signUp("a@b.co", "password1")).rejects.toMatchObject({ code: "auth/email-already-in-use" });
  });
  it.each(["auth/wrong-password", "auth/user-not-found"])("existing email + %s sign-in error reports email-already-in-use", async (code) => {
    m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
    m.signIn.mockRejectedValue({ code });
    await expect(make().signUp("a@b.co", "password1")).rejects.toMatchObject({ code: "auth/email-already-in-use" });
  });
  it.each(["auth/too-many-requests", "auth/network-request-failed", "auth/user-disabled", "auth/internal-error"])(
    "existing email + %s sign-in error surfaces that error, not email-already-in-use",
    async (code) => {
      m.createUser.mockRejectedValue({ code: "auth/email-already-in-use" });
      m.signIn.mockRejectedValue({ code });
      await expect(make().signUp("a@b.co", "password1")).rejects.toMatchObject({ code });
    },
  );
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

describe("firebase email endpoints", () => {
  it("sendVerificationEmail POSTs with the current user's ID token", async () => {
    await make().sendVerificationEmail("/x");
    const req = sent();
    expect(req.method).toBe("POST");
    expect(new URL(req.url).pathname).toBe("/v1/auth/email/verification");
    expect(req.headers.get("authorization")).toBe("Bearer t");
    expect(await req.json()).toEqual({ next: "/x" });
  });
  it("sendVerificationEmail with nobody signed in rejects without calling the API", async () => {
    auth.currentUser = null;
    await expect(make().sendVerificationEmail()).rejects.toMatchObject({ code: "auth/requires-recent-login" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("sendVerificationEmail maps 429 to email/rate-limited", async () => {
    reply(429, { error: { code: "rate_limited" } });
    await expect(make().sendVerificationEmail()).rejects.toMatchObject({ code: "email/rate-limited" });
  });
  it.each([503, 500])("sendVerificationEmail maps %i to email/unavailable", async (status) => {
    reply(status);
    await expect(make().sendVerificationEmail()).rejects.toMatchObject({ code: "email/unavailable" });
  });
  it("sendVerificationEmail maps a network failure to email/unavailable", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(make().sendVerificationEmail()).rejects.toMatchObject({ code: "email/unavailable" });
  });
  it("sendPasswordReset POSTs the email with no Authorization header", async () => {
    await make().sendPasswordReset("a@b.co");
    const req = sent();
    expect(new URL(req.url).pathname).toBe("/v1/auth/email/password-reset");
    expect(req.headers.get("authorization")).toBeNull();
    expect(await req.json()).toEqual({ email: "a@b.co" });
    expect(currentUser.getIdToken).not.toHaveBeenCalled();
  });
  it("sendPasswordReset works signed out and resolves the same for any 202", async () => {
    auth.currentUser = null;
    await expect(make().sendPasswordReset("nobody@b.co")).resolves.toBeUndefined();
  });
  it("sendPasswordReset maps 429 and 503/network to the email/* codes", async () => {
    reply(429);
    await expect(make().sendPasswordReset("a@b.co")).rejects.toMatchObject({ code: "email/rate-limited" });
    reply(503);
    await expect(make().sendPasswordReset("a@b.co")).rejects.toMatchObject({ code: "email/unavailable" });
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(make().sendPasswordReset("a@b.co")).rejects.toMatchObject({ code: "email/unavailable" });
  });
});

describe("createFirebaseAuthService without emailApi", () => {
  const bare = () => createFirebaseAuthService({ apiKey: "AIzaSy", authDomain: "d", projectId: "p", appId: "a" }, { emailApi: null });

  it("password reset and verification email reject with email/unavailable and never call the network", async () => {
    await expect(bare().sendPasswordReset("a@b.co")).rejects.toMatchObject({ code: "email/unavailable" });
    await expect(bare().sendVerificationEmail()).rejects.toMatchObject({ code: "email/unavailable" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sign-in and sign-up still work (sign-up tolerates the missing verification email)", async () => {
    m.createUser.mockResolvedValue({ user: currentUser });
    const svc = bare();
    await svc.signIn("a@b.co", "pw");
    expect(m.signIn).toHaveBeenCalled();
    await expect(svc.signUp("a@b.co", "pw")).resolves.toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a supplied emailApi is used instead of the default client", async () => {
    const post = vi.fn().mockResolvedValue({ response: { status: 202 } });
    const svc = createFirebaseAuthService(
      { apiKey: "AIzaSy", authDomain: "d", projectId: "p", appId: "a" },
      { emailApi: () => ({ POST: post }) as never },
    );
    await svc.sendPasswordReset("a@b.co");
    expect(post).toHaveBeenCalledWith("/auth/email/password-reset", { body: { email: "a@b.co" } });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
