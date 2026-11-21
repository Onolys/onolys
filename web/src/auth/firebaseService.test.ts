import { beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = { reload: vi.fn(), getIdToken: vi.fn(), emailVerified: true, uid: "u", email: "a@b.co" };
const auth = { currentUser: currentUser as unknown | null, authStateReady: () => Promise.resolve() };
const m = {
  applyActionCode: vi.fn(),
  verifyPasswordResetCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  reload: vi.fn(),
};

vi.mock("firebase/app", () => ({ initializeApp: () => ({}) }));
vi.mock("firebase/auth", () => ({
  GoogleAuthProvider: class {},
  getAuth: () => auth,
  getRedirectResult: () => Promise.resolve(null),
  onIdTokenChanged: vi.fn(),
  applyActionCode: (...a: unknown[]) => m.applyActionCode(...a),
  verifyPasswordResetCode: (...a: unknown[]) => m.verifyPasswordResetCode(...a),
  confirmPasswordReset: (...a: unknown[]) => m.confirmPasswordReset(...a),
  reload: (...a: unknown[]) => m.reload(...a),
  createUserWithEmailAndPassword: vi.fn(),
  sendEmailVerification: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
  signInWithEmailAndPassword: vi.fn(),
  signInWithPopup: vi.fn(),
  signInWithRedirect: vi.fn(),
  signOut: vi.fn(),
}));

import { createFirebaseAuthService } from "./firebaseService";

const make = () => createFirebaseAuthService({ apiKey: "AIzaSy", authDomain: "d", projectId: "p", appId: "a" });

beforeEach(() => {
  vi.clearAllMocks();
  auth.currentUser = currentUser;
  currentUser.getIdToken.mockResolvedValue("t");
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
