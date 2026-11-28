/**
 * Public contact address: footer, legal pages and Settings account-removal requests. `VITE_CONTACT_EMAIL`
 * overrides the default, which is the address the landing-page footer already shows.
 */
export const CONTACT_EMAIL: string = import.meta.env.VITE_CONTACT_EMAIL || "tejitpabari99@gmail.com";

/**
 * Build-time switch for every clinician-rating UI (`VITE_RATING_ENABLED`, absent = off). A function, not a
 * constant, so tests can `vi.stubEnv` it.
 */
export const ratingEnabled = (): boolean => import.meta.env.VITE_RATING_ENABLED === "true";

/** App hosts a sign-in email link may return to when it was sent from another environment. */
const DEFAULT_APP_HOSTS = ["app.onolys.com", "onolys-app.web.app", "onolys-staging-app.web.app"];

/**
 * Hosts (besides this origin) an email-action continue link may send the user back to: the Firebase auth domain plus the
 * comma-separated hostnames in `VITE_APP_HOSTS` (the three Onolys app hosts when that is unset or empty), lowercase.
 */
export function appHosts(env: Record<string, string | undefined> = import.meta.env): string[] {
  const configured = (env.VITE_APP_HOSTS ?? "").split(",").map((h) => h.trim().toLowerCase()).filter(Boolean);
  const extra = configured.length > 0 ? configured : DEFAULT_APP_HOSTS;
  return [...new Set([env.VITE_FIREBASE_AUTH_DOMAIN, ...extra].map((h) => (h ?? "").trim().toLowerCase()).filter(Boolean))];
}
