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
