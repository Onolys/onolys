import { useEffect, useRef, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { AppHeader, SkipLink } from "@onolys/ui";
import { useAuth } from "../auth/AuthProvider";
import { useSignOut } from "../auth/useSignOut";
import { AccountMenu } from "./AccountMenu";
import { Footer } from "./Footer";
import { RouteTitle } from "./routeTitle";

/** Plain text nav link (not a button): muted, subtle hover, current page = primary colour + underline. AppHeader's nav supplies the even gap. */
function NavItem({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className="text-sm font-medium text-muted-foreground no-underline hover:text-foreground aria-[current=page]:text-primary aria-[current=page]:underline aria-[current=page]:decoration-2 aria-[current=page]:underline-offset-8"
    >
      {children}
    </NavLink>
  );
}

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

  let navigation: ReactNode = null; // loading and unverified: brand only (verify is not a signed-in state)
  if (phase === "signedOut") {
    navigation = (
      <>
        <NavItem to="/login">Log in</NavItem>
        <NavItem to="/signup">Sign up</NavItem>
      </>
    );
  } else if (phase === "verified") {
    navigation = (
      <>
        <NavItem to="/new">New Session</NavItem>
        <NavItem to="/sessions">Sessions</NavItem>
      </>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <RouteTitle />
      <SkipLink />
      <AppHeader
        // verified: page nav sits at the true centre of the bar (brand left, account menu right); signed-out nav stays right via the brand's mr-auto
        className={phase === "verified" ? "relative [&>nav]:absolute [&>nav]:left-1/2 [&>nav]:-translate-x-1/2" : undefined}
        brand={
          <Link to="/" className="font-bold text-primary no-underline">
            Onolys
          </Link>
        }
        navigation={navigation}
        accountMenu={phase === "verified" ? <AccountMenu email={user?.email ?? null} onSignOut={() => void signOut()} /> : undefined}
      />
      {signOutError && <p role="alert">{signOutError}</p>}
      <main
        id="main"
        ref={mainRef}
        // focus-to-h1 on route change: no ring for programmatic focus, keep it for keyboard focus-visible
        className={`mx-auto w-full flex-1 px-4 py-6 [&_h1:focus:not(:focus-visible)]:outline-none ${pathname === "/sample" || /^\/sessions\/[^/]+\/reports\/[^/]+$/.test(pathname) ? "max-w-none lg:w-4/5" : "max-w-5xl"}`}
      >
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
