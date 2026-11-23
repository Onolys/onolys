/** Account-removal requests go here. A placeholder until the launch address is set (`VITE_CONTACT_EMAIL`). */
export const CONTACT_EMAIL: string = import.meta.env.VITE_CONTACT_EMAIL || "[contact address set before launch]";
export const HAS_CONTACT_EMAIL = Boolean(import.meta.env.VITE_CONTACT_EMAIL);

/**
 * Build-time switch for every clinician-rating UI (`VITE_RATING_ENABLED`, absent = off). A function, not a
 * constant, so tests can `vi.stubEnv` it.
 */
export const ratingEnabled = (): boolean => import.meta.env.VITE_RATING_ENABLED === "true";

/** Public contact address shown in the footer and legal pages. `VITE_CONTACT_EMAIL` overrides the default. */
export const SUPPORT_EMAIL: string = import.meta.env.VITE_CONTACT_EMAIL || "tejitpabari99@gmail.com";
