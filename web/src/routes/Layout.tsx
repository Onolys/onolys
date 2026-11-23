import { useEffect, useRef, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { AppHeader, Button, SkipLink, cn } from "@onolys/ui";
import { useAuth } from "../auth/AuthProvider";
import { useSignOut } from "../auth/useSignOut";
import { AccountMenu } from "./AccountMenu";
import { Footer } from "./Footer";

type Variant = "default" | "outline" | "ghost";

/** Sample report always opens in a new tab (safe form), whatever the phase. */
function SampleLink({ className }: { className?: string }) {
  return (
    <Button asChild variant="outline" size="sm" className={cn("no-underline", className)}>
      <Link to="/sample" target="_blank" rel="noopener noreferrer">
        Sample report
      </Link>
    </Button>
  );
}

function NavButton({ to, variant, className, children }: { to: string; variant: Variant; className?: string; children: ReactNode }) {
  return (
    <Button asChild variant={variant} size="sm" className={cn("no-underline", className)}>
      <NavLink to={to} end>
        {children}
      </NavLink>
    </Button>
  );
}

const CURRENT = "aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground aria-[current=page]:hover:bg-primary";

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
    // Sample report centered in the free space; Log in + Sign up pushed to the far right.
    navigation = (
      <>
        <SampleLink className="mx-auto" />
        <NavButton to="/login" variant="ghost" className="ml-auto">
          Log in
        </NavButton>
        <NavButton to="/signup" variant="default">
          Sign up
        </NavButton>
      </>
    );
  } else if (phase === "verified") {
    navigation = (
      <>
        <NavButton to="/sessions" variant="outline" className={CURRENT}>
          Sessions
        </NavButton>
        <NavButton to="/new" variant="outline" className={CURRENT}>
          New Session
        </NavButton>
        <SampleLink />
      </>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <AppHeader
        // signed-out: let the nav fill the header so Sample can center and Log in/Sign up sit right
        className={phase === "signedOut" ? "[&>nav]:min-w-0 [&>nav]:flex-1" : undefined}
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
        className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 [&_h1:focus:not(:focus-visible)]:outline-none"
      >
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
