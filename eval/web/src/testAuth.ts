import type { AuthService } from '@onolys/common/auth';
import { createTestAuthService, signUpTestUser } from '@onolys/common/auth/testing';
import { afterEach, vi } from 'vitest';

/** Services made in this test file: every one shares one Firebase app, so each is signed out again after the test. */
const made: AuthService[] = [];
afterEach(async () => { await Promise.all(made.splice(0).map(s => s.signOut())); });

/** jsdom cannot finish the SDK's redirect check; the real service answers "no failed redirect" instead. */
function emulatorService(): AuthService {
  const service = createTestAuthService();
  vi.spyOn(service, 'consumeRedirectError').mockResolvedValue(undefined);
  made.push(service);
  return service;
}

/** The real Firebase service on the Auth emulator, nobody signed in. Run tests under `firebase emulators:exec --only auth`. */
export const signedOutService = emulatorService;

/** The real service with a fresh account signed in (verified unless told otherwise). */
export async function signedInService(verified = true): Promise<AuthService> {
  const service = emulatorService();
  await signUpTestUser(service, { verified });
  return service;
}
