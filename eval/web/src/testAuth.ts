import type { AuthService } from '@onolys/common/auth';
import { createTestAuthService, signOutTestServices, signUpTestUser } from '@onolys/common/auth/testing';
import { afterEach } from 'vitest';

afterEach(signOutTestServices);

/** The real Firebase service on the Auth emulator, nobody signed in. Run tests under `firebase emulators:exec --only auth`. */
export const signedOutService = (): AuthService => createTestAuthService();

/** The real service with a fresh account signed in (verified unless told otherwise). */
export async function signedInService(verified = true): Promise<AuthService> {
  const service = createTestAuthService();
  await signUpTestUser(service, { verified });
  return service;
}
