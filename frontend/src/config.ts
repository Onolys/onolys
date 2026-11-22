export interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
}

export interface AppConfig {
  /** true only when VITE_MOCK is exactly "true": gate off, no backend call (local dev). */
  mock: boolean;
  /** Origin of the admin backend (VITE_ADMIN_API_URL), no path. null when unset. */
  adminApiUrl: string | null;
}

export interface AuthConfig {
  /** true only when VITE_AUTH_REQUIRED is exactly "true" (deployed admin build). */
  authRequired: boolean;
  firebase: FirebaseConfig;
}

export function getConfig(): AppConfig & AuthConfig {
  const { VITE_MOCK, VITE_ADMIN_API_URL, VITE_AUTH_REQUIRED } = import.meta.env;
  const { VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID, VITE_FIREBASE_APP_ID } = import.meta.env;
  return {
    authRequired: VITE_AUTH_REQUIRED === "true",
    firebase: {
      apiKey: VITE_FIREBASE_API_KEY ?? "",
      authDomain: VITE_FIREBASE_AUTH_DOMAIN || "admin.onolys.com",
      projectId: VITE_FIREBASE_PROJECT_ID ?? "",
      appId: VITE_FIREBASE_APP_ID ?? "",
    },
    mock: VITE_MOCK === "true",
    adminApiUrl: VITE_ADMIN_API_URL ? VITE_ADMIN_API_URL : null,
  };
}
