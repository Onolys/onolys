import { describe, expect, it } from "vitest";
import { createFakeAuthService } from "./fakeService";

describe("fake auth service", () => {
  it("signs up unverified, sends a verification email, and issues SP04 fake tokens", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    expect(s.calls.verificationEmails).toBe(1);
    expect(await s.getToken()).toMatch(/^test:u_/);
    let seen: unknown = "none";
    s.onAuthStateChanged((u) => (seen = u));
    await Promise.resolve();
    expect(seen).toMatchObject({ email: "a@b.co", emailVerified: false });
  });
  it("rejects duplicates and bad passwords with firebase-style codes", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    await s.signOut();
    await expect(s.signUp("a@b.co", "otherpass1")).rejects.toMatchObject({ code: "auth/email-already-in-use" });
    await expect(s.signIn("a@b.co", "nope")).rejects.toMatchObject({ code: "auth/invalid-credential" });
  });
  it("sign-up with an existing email and the right password signs in, without another verification email", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    await s.signOut();
    let seen: unknown = "none";
    s.onAuthStateChanged((u) => (seen = u));
    await s.signUp("a@b.co", "password1");
    expect(seen).toMatchObject({ email: "a@b.co", emailVerified: false });
    expect(s.calls.verificationEmails).toBe(1);
  });
  it("refreshUser counts a forced token refresh and picks up server-side verification", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    s.markVerified("a@b.co");
    const u = await s.refreshUser();
    expect(u?.emailVerified).toBe(true);
    expect(s.calls.forcedRefreshes).toBe(1);
  });
  it("signOut clears the user and the token", async () => {
    const s = createFakeAuthService();
    s.signedInAs("a@b.co", { verified: true });
    await s.signOut();
    expect(await s.getToken()).toBeNull();
  });
  it("applyEmailVerification consumes the code, verifies and refreshes the signed-in user", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    const code = s.issueActionCode("verifyEmail", "a@b.co");
    await s.applyEmailVerification(code);
    expect((await s.refreshUser())?.emailVerified).toBe(true);
    await expect(s.applyEmailVerification(code)).rejects.toMatchObject({ code: "auth/invalid-action-code" });
    const old = s.issueActionCode("verifyEmail", "a@b.co", { expired: true });
    await expect(s.applyEmailVerification(old)).rejects.toMatchObject({ code: "auth/expired-action-code" });
  });
  it("password reset: verify returns the email without consuming; confirm sets the password", async () => {
    const s = createFakeAuthService();
    await s.signUp("a@b.co", "password1");
    await s.signOut();
    const code = s.issueActionCode("resetPassword", "a@b.co");
    expect(await s.verifyPasswordResetCode(code)).toBe("a@b.co");
    await s.confirmPasswordReset(code, "newpassword1");
    await s.signIn("a@b.co", "newpassword1");
    await expect(s.confirmPasswordReset(code, "again1234")).rejects.toMatchObject({ code: "auth/invalid-action-code" });
  });
  it("verifyAndChangeEmail: check shows the new email without consuming; apply changes the account and signs the user out", async () => {
    const s = createFakeAuthService();
    s.signedInAs("a@b.co", { verified: true });
    const code = s.issueActionCode("verifyAndChangeEmail", "a@b.co", { newEmail: "n@b.co" });
    expect(await s.checkEmailChangeCode(code, "verifyAndChangeEmail")).toEqual({ email: "n@b.co", previousEmail: "a@b.co" });
    expect(s.calls.emailChanges).toBe(0);
    expect(await s.applyEmailChange(code)).toEqual({ signedIn: false });
    expect(s.calls.emailChanges).toBe(1);
    expect(await s.getToken()).toBeNull();
    await expect(s.signIn("a@b.co", "password1")).rejects.toMatchObject({ code: "auth/invalid-credential" });
    await s.signIn("n@b.co", "password1");
    await expect(s.applyEmailChange(code)).rejects.toMatchObject({ code: "auth/invalid-action-code" });
  });
  it("recoverEmail: check returns the restored email; apply restores it; wrong kind and expired codes are rejected", async () => {
    const s = createFakeAuthService();
    await s.signUp("new@b.co", "password1");
    await s.signOut();
    const code = s.issueActionCode("recoverEmail", "new@b.co", { previousEmail: "old@b.co" });
    await expect(s.checkEmailChangeCode(code, "verifyAndChangeEmail")).rejects.toMatchObject({ code: "auth/invalid-action-code" });
    expect(await s.checkEmailChangeCode(code, "recoverEmail")).toEqual({ email: "old@b.co", previousEmail: "new@b.co" });
    await s.applyEmailChange(code);
    await s.signIn("old@b.co", "password1");
    const old = s.issueActionCode("recoverEmail", "old@b.co", { previousEmail: "x@b.co", expired: true });
    await expect(s.checkEmailChangeCode(old, "recoverEmail")).rejects.toMatchObject({ code: "auth/expired-action-code" });
  });
});
