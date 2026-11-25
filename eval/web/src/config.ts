export interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
}
export function getConfig() {
  const env = import.meta.env;
  return {
    evalApiUrl: (env.VITE_EVAL_API_URL ?? '').replace(/\/$/, ''),
    /** Prod app: sign-up, email verification and password reset live there. */
    appUrl: (env.VITE_APP_URL || 'https://app.onolys.com').replace(/\/$/, ''),
    firebase: {
      apiKey: env.VITE_FIREBASE_API_KEY ?? '',
      authDomain: env.VITE_FIREBASE_AUTH_DOMAIN || 'eval.onolys.com',
      projectId: env.VITE_FIREBASE_PROJECT_ID ?? '',
      appId: env.VITE_FIREBASE_APP_ID ?? '',
    } satisfies FirebaseConfig,
  };
}
