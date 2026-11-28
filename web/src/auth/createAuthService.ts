import type { AuthService } from "@onolys/common/auth";
import type { EmailApi } from "@onolys/common/auth/firebase";
import { apiBaseUrl, createApiClient } from "../api/client";

/** The server-sent email routes through the typed API client; each answers the HTTP status (the service maps non-2xx). */
export function createEmailApi(baseUrl: string = apiBaseUrl()): EmailApi {
  return {
    async sendVerification(getIdToken, next) {
      const client = createApiClient({ baseUrl, getToken: () => getIdToken(), onSessionExpired: () => {} });
      return (await client.POST("/auth/email/verification", { body: { next } })).response.status;
    },
    async sendPasswordReset(email) {
      const client = createApiClient({ baseUrl, getToken: async () => null, onSessionExpired: () => {} });
      return (await client.POST("/auth/email/password-reset", { body: { email } })).response.status;
    },
  };
}

/**
 * Firebase from `VITE_FIREBASE_*`; set `VITE_FIREBASE_AUTH_EMULATOR_URL` (mock mode, local dev) to use the Auth emulator
 * instead. Firebase is loaded lazily.
 */
export async function createAuthService(env: ImportMetaEnv = import.meta.env): Promise<AuthService> {
  const { createFirebaseAuthService } = await import("@onolys/common/auth/firebase");
  return createFirebaseAuthService(
    {
      apiKey: env.VITE_FIREBASE_API_KEY,
      authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: env.VITE_FIREBASE_PROJECT_ID,
      appId: env.VITE_FIREBASE_APP_ID,
    },
    { emailApi: createEmailApi(), emulatorUrl: env.VITE_FIREBASE_AUTH_EMULATOR_URL || undefined },
  );
}
