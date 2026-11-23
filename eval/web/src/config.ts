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
    firebase: {
      apiKey: env.VITE_FIREBASE_API_KEY ?? '',
      authDomain: env.VITE_FIREBASE_AUTH_DOMAIN || 'admin.onolys.com',
      projectId: env.VITE_FIREBASE_PROJECT_ID ?? '',
      appId: env.VITE_FIREBASE_APP_ID ?? '',
    } satisfies FirebaseConfig,
  };
}
