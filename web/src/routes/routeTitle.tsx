import { useEffect } from "react";
import { matchPath, useLocation } from "react-router";

const SITE = "Onolys";

/** Page names by route, first match wins. Fixed text only: a title never carries an id, a goal or anything from the person's data (no PHI in titles). */
const PAGES: readonly (readonly [pattern: string, name: string])[] = [
  ["/new", "New session"],
  ["/sessions", "Sessions"],
  ["/sessions/new", "Upload a session"],
  ["/sessions/:id", "Session"],
  ["/sessions/:id/reports/:version", "Report"],
  ["/interviews/new", "New interview"],
  ["/interviews/:id", "Interview"],
  ["/settings", "Settings"],
  ["/login", "Log in"],
  ["/signup", "Sign up"],
  ["/forgot-password", "Reset password"],
  ["/verify-email", "Verify your email"],
  ["/auth/action", "Account"],
  ["/privacy", "Privacy policy"],
  ["/terms", "Terms of service"],
  ["/sample", "Sample report"],
];

export function titleForPath(pathname: string): string {
  if (pathname === "/") return SITE;
  const hit = PAGES.find(([pattern]) => matchPath({ path: pattern, end: true }, pathname));
  return `${hit ? hit[1] : "Page not found"} · ${SITE}`;
}

/** Keeps the browser tab title in step with the route; renders nothing. */
export function RouteTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titleForPath(pathname);
  }, [pathname]);
  return null;
}
