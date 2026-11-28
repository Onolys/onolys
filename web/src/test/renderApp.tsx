import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { AuthProvider, type AuthService } from "@onolys/common/auth";
import type { EmailApi } from "@onolys/common/auth/firebase";
import { createTestAuthService, EMULATOR_URL, TEST_PASSWORD, TEST_PROJECT_ID } from "@onolys/common/auth/testing";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { afterEach, expect, vi } from "vitest";
import { clearJobs } from "../features/upload/uploader";
import { uidFromToken } from "../mocks/handlers";
import { makeQueryClient } from "../queryClient";
import { routes } from "../routes/routes";

export interface RenderOptions {
  /** Defaults to a new emulator-backed service. */
  service?: AuthService;
  /** Email routes for the default service (none by default: sign-up still works, the email flows say "unavailable"). */
  emailApi?: EmailApi | null;
  /** Pre-signed-in user, signed in through the real service. Omit for signed out. */
  user?: { email: string; verified: boolean; displayName?: string | null };
  /** Route table to render instead of the app routes (page-level tests). */
  routes?: RouteObject[];
}

/** Stands in for the app's email routes (the one thing the emulator does not run): answers `status`, or throws it. */
export function stubEmailApi(status: number | Error = 202) {
  const answer = async () => {
    if (status instanceof Error) throw status;
    return status;
  };
  return {
    sendVerification: vi.fn<EmailApi["sendVerification"]>(async (getIdToken) => {
      await getIdToken();
      return answer();
    }),
    sendPasswordReset: vi.fn<EmailApi["sendPasswordReset"]>(async () => answer()),
  } satisfies EmailApi;
}

const made: AuthService[] = [];
// Every service in a test file shares one Firebase app: leave nobody signed in for the next test.
// Unmount first: pages flush pending work (autosave) on unmount and that still needs the signed-in user.
afterEach(async () => {
  cleanup();
  await Promise.all(made.splice(0).map((s) => s.signOut()));
});

/** jsdom cannot finish the SDK's redirect check (it answers auth/operation-not-supported-in-this-environment). */
function noRedirectCheck(service: AuthService) {
  service.consumeRedirectError = async () => undefined;
}

/** A new emulator-backed service, signed out again after the test. */
export function testService(emailApi: EmailApi | null = null): AuthService {
  const service = createTestAuthService(emailApi);
  noRedirectCheck(service);
  made.push(service);
  return service;
}

/** The user id (`sub`) of the signed-in user's ID token. */
export async function uidOf(service: AuthService): Promise<string> {
  const uid = uidFromToken((await service.getToken()) ?? "");
  if (!uid) throw new Error("not signed in");
  return uid;
}

/**
 * Vitest runs test files in parallel against ONE auth emulator, so two files must never share an account (one file's
 * verified/name rewrite would race the other's sign-in). A short tag of the test file's path keeps each file's accounts apart.
 */
function fileTag(): string {
  const path = expect.getState().testPath;
  if (!path) throw new Error("test accounts need a test file (expect.getState().testPath is unset)");
  let h = 2166136261; // FNV-1a
  for (let i = 0; i < path.length; i++) h = Math.imul(h ^ path.charCodeAt(i), 16777619) >>> 0;
  return h.toString(36).padStart(7, "0");
}

/** `rater@clinic.org` -> `rater@<file tag>.clinic.org`: the account this test file uses for that logical user. */
export const testEmail = (email: string) => {
  const at = email.lastIndexOf("@");
  // Tag the domain, not the local part: the page greets the user by the local part ("Welcome rater").
  return `${email.slice(0, at)}@${fileTag()}.${email.slice(at + 1)}`.toLowerCase();
};

/** `rater@clinic.org` -> `u_rater_<tag>_clinic_org`: tests seed the mock backend under this id before the page renders. */
export const uidForEmail = (email: string) => `u_${testEmail(email).replace(/[^a-z0-9]+/g, "_")}`;

const admin = (path: string, body: object) =>
  fetch(`${EMULATOR_URL}/identitytoolkit.googleapis.com/v1/${path}?key=fake-api-key`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: "Bearer owner" },
    body: JSON.stringify(body),
  });

/**
 * Signs `email` in through the real service. The account is made (or updated) through the emulator's admin REST API so
 * its id is `uidForEmail(email)` and its verified state and name are what the test asks for.
 */
export async function signInTestUser(service: AuthService, user: NonNullable<RenderOptions["user"]>) {
  const localId = uidForEmail(user.email);
  const email = testEmail(user.email);
  await admin("accounts:signUp", { email, password: TEST_PASSWORD, localId }); // already there is fine
  const update = await admin(`projects/${TEST_PROJECT_ID}/accounts:update`, {
    localId,
    emailVerified: user.verified,
    ...(user.displayName ? { displayName: user.displayName } : { deleteAttribute: ["DISPLAY_NAME"] }),
  });
  if (!update.ok) throw new Error(`Auth emulator account update answered ${update.status}`);
  await service.signIn(email, TEST_PASSWORD);
}

export async function renderApp(path: string, opts: RenderOptions = {}) {
  const service = opts.service ?? testService(opts.emailApi ?? null);
  if (!made.includes(service)) made.push(service);
  noRedirectCheck(service);
  if (opts.user) await signInTestUser(service, opts.user);
  const queryClient = makeQueryClient();
  const router = createMemoryRouter(opts.routes ?? routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={service} onSignOut={clearJobs}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { router, service, queryClient };
}

export function here(router: { state: { location: { pathname: string; search: string } } }) {
  return router.state.location.pathname + router.state.location.search;
}
