import { EMULATOR_URL, newTestEmail, TEST_PASSWORD, TEST_PROJECT_ID } from "@onolys/common/auth/testing";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { uidFromToken } from "../mocks/handlers";
import { server } from "../mocks/server";
import { createAuthService } from "./createAuthService";

const ENV = {
  VITE_FIREBASE_API_KEY: "fake-api-key",
  VITE_FIREBASE_AUTH_DOMAIN: `${TEST_PROJECT_ID}.firebaseapp.com`,
  VITE_FIREBASE_PROJECT_ID: TEST_PROJECT_ID,
  VITE_FIREBASE_APP_ID: "1:1:web:1",
  VITE_FIREBASE_AUTH_EMULATOR_URL: EMULATOR_URL,
} as unknown as ImportMetaEnv;

const made: { signOut(): Promise<void> }[] = [];
afterEach(async () => {
  await Promise.all(made.splice(0).map((s) => s.signOut()));
});
async function service() {
  const s = await createAuthService(ENV);
  s.consumeRedirectError = async () => undefined; // jsdom cannot finish the SDK's redirect check
  made.push(s);
  return s;
}

describe("createAuthService email routes", () => {
  it("sign-up asks the verification route for an email with the new user's ID token", async () => {
    const calls: { auth: string | null; body: unknown }[] = [];
    server.use(
      http.post("*/v1/auth/email/verification", async ({ request }) => {
        calls.push({ auth: request.headers.get("authorization"), body: await request.json() });
        return new HttpResponse(null, { status: 202 });
      }),
    );
    const s = await service();
    await s.signUp(newTestEmail(), TEST_PASSWORD, "/sessions");
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ next: "/sessions" });
    const uid = uidFromToken((calls[0].auth ?? "").replace(/^Bearer /, ""));
    expect(uid).toBeTruthy();
    expect(uidFromToken(((await s.getToken()) ?? ""))).toBe(uid);
  });

  it("the password-reset route gets the address and no token", async () => {
    const calls: { auth: string | null; body: unknown }[] = [];
    server.use(
      http.post("*/v1/auth/email/password-reset", async ({ request }) => {
        calls.push({ auth: request.headers.get("authorization"), body: await request.json() });
        return new HttpResponse(null, { status: 202 });
      }),
    );
    const s = await service();
    await s.sendPasswordReset("a@clinic.org");
    expect(calls).toEqual([{ auth: null, body: { email: "a@clinic.org" } }]);
  });

  it.each([429, 503])("a %i from either route is an email/unavailable rejection", async (status) => {
    server.use(
      http.post("*/v1/auth/email/password-reset", () => new HttpResponse(null, { status })),
      http.post("*/v1/auth/email/verification", () => new HttpResponse(null, { status })),
    );
    const s = await service();
    await expect(s.sendPasswordReset("a@clinic.org")).rejects.toMatchObject({ code: "email/unavailable" });
    await s.signUp(newTestEmail(), TEST_PASSWORD); // the account is made even when the email is not
    await expect(s.sendVerificationEmail()).rejects.toMatchObject({ code: "email/unavailable" });
  });
});
