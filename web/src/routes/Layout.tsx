import { useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useAuth, type AuthPhase } from "../auth/AuthProvider";
import { useSignOut } from "../auth/useSignOut";
import { AccountMenu } from "./AccountMenu";
import { Footer } from "./Footer";

const NAV: Record<AuthPhase, { to: string; label: string; className?: string; external?: boolean }[]> = {
  loading: [],
  signedOut: [
    { to: "/sample", label: "Sample report", className: "btn btn-secondary nav-sample", external: true },
    { to: "/login", label: "Log in", className: "nav-login" },
    { to: "/signup", label: "Sign up", className: "btn btn-primary nav-signup" },
  ],
  unverified: [], // the verify screen is not a signed-in state: brand only
  verified: [
    { to: "/sessions", label: "Sessions", className: "btn btn-secondary nav-btn" },
    { to: "/new", label: "New Session", className: "btn btn-secondary nav-btn" },
    { to: "/sample", label: "Sample report", className: "btn btn-secondary nav-btn nav-sample", external: true },
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
        <nav aria-label="Main" className={phase === "signedOut" ? "nav-out" : undefined}>
          {NAV[phase].map((l) =>
            l.external ? (
              <Link key={l.to} to={l.to} target="_blank" rel="noopener noreferrer" className={l.className}>
                {l.label}
              </Link>
            ) : (
              <NavLink key={l.to} to={l.to} end className={l.className}>
                {l.label}
              </NavLink>
            ),
          )}
        </nav>
        {phase === "verified" && <AccountMenu email={user?.email ?? null} onSignOut={() => void signOut()} />}
      </header>
      {signOutError && <p role="alert">{signOutError}</p>}
      <main id="main" ref={mainRef}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
