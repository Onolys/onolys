import { useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useAuth, type AuthPhase } from "../auth/AuthProvider";
import { useSignOut } from "../auth/useSignOut";

const NAV: Record<AuthPhase, { to: string; label: string }[]> = {
  loading: [],
  signedOut: [
    { to: "/login", label: "Log in" },
    { to: "/signup", label: "Sign up" },
    { to: "/sample-report", label: "Sample report" },
  ],
  unverified: [{ to: "/verify-email", label: "Verify email" }],
  verified: [
    { to: "/", label: "Sessions" },
    { to: "/sessions/new", label: "New session" },
    { to: "/settings", label: "Settings" },
  ],
};

export function Layout() {
  const { pathname } = useLocation();
  const { status, phase, user } = useAuth();
  const { signOut, error: signOutError } = useSignOut();
  const mainRef = useRef<HTMLElement>(null);

  // A11y (R8): after each route change move focus to the page h1.
  useEffect(() => {
    const h1 = mainRef.current?.querySelector("h1");
    if (h1) {
      h1.setAttribute("tabindex", "-1");
      h1.focus();
    }
  }, [pathname, status]);

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="app-header">
        <Link to="/" className="brand">
          Onolys
        </Link>
        <nav aria-label="Main">
          {NAV[phase].map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/"}>
              {l.label}
            </NavLink>
          ))}
          {(phase === "verified" || phase === "unverified") && (
            <>
              {user?.email && <span className="nav-user">{user.email}</span>}
              <button type="button" className="btn btn-secondary" onClick={() => void signOut()}>
                Sign out
              </button>
            </>
          )}
        </nav>
      </header>
      {signOutError && <p role="alert">{signOutError}</p>}
      <main id="main" ref={mainRef}>
        <Outlet />
      </main>
      <footer className="app-footer">
        <p>Onolys</p>
      </footer>
    </div>
  );
}
