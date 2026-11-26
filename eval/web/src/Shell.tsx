import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router';
import { AppHeader, Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger, Footer, SkipLink } from '@onolys/ui';
import { useAuth } from '@prod-auth/AuthProvider';
import { useSignOut } from '@prod-auth/useSignOut';
import { ErrorBoundary } from './ErrorPage';
import { ThemeToggle } from '@prod-routes/ThemeToggle';

/** Same plain-text tab style as the prod nav (web/src/routes/Layout.tsx NavItem). */
const NAV_LINK = 'text-sm font-medium text-muted-foreground no-underline hover:text-foreground aria-[current=page]:text-primary aria-[current=page]:underline aria-[current=page]:decoration-2 aria-[current=page]:underline-offset-8';

/** Eval page chrome: header, nav and account menu around the routed content. */
export function Shell() {
  const { phase, user } = useAuth();
  const { signOut, error } = useSignOut();
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState(window.location.search);
  useEffect(() => {
    const update = () => setQuery(window.location.search);
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  const signedIn = phase === 'verified' || phase === 'unverified';
  const navigate = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    window.history.pushState({}, '', event.currentTarget.href);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };
  const location = useLocation();
  /** Eval has one page, served at "/": links always go there, even from an unknown path (404). */
  const link = (history = false) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('run'); url.searchParams.delete('view');
    if (history) url.searchParams.set('view', 'history');
    return '/' + url.search;
  };
  const historySelected = new URLSearchParams(query).get('view') === 'history' || new URLSearchParams(query).has('run');
  return <div className="shell flex min-h-screen flex-col">
    <SkipLink />
    <AppHeader
      // signed in: page tabs sit at the true centre of the bar (brand left, account menu right), as in the prod app
      className={phase === 'verified' ? 'relative [&>nav]:absolute [&>nav]:left-1/2 [&>nav]:-translate-x-1/2' : undefined}
      brand={<a className="font-bold text-primary no-underline" href={link()} onClick={navigate}>Onolys<span className="ml-2 text-sm font-normal text-muted-foreground">Evaluation</span></a>}
      navigation={phase === 'verified' ? <><a className={NAV_LINK} href={link()} onClick={navigate} aria-current={!historySelected ? 'page' : undefined}>New Run</a><a className={NAV_LINK} href={link(true)} onClick={navigate} aria-current={historySelected ? 'page' : undefined}>History</a></> : undefined}
      accountMenu={signedIn ? <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <Button asChild size="icon" className="rounded-full font-semibold"><DropdownMenuTrigger aria-label="Account menu">{(user?.email?.[0] ?? '?').toUpperCase()}</DropdownMenuTrigger></Button>
        <DropdownMenuContent align="end" className="min-w-56 max-w-80">
          {user?.email && <DropdownMenuLabel className="font-normal break-words text-muted-foreground">{user.email}</DropdownMenuLabel>}
          <DropdownMenuItem onSelect={() => void signOut()}>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu> : undefined} />
    {error && <p role="alert">{error}</p>}
    {/* signed-out pages (login) use the prod page width; the signed-in app uses the prod wide-page width */}
    <main id="main" className={`eval-main mx-auto w-full flex-1 px-4 py-6 ${signedIn ? 'max-w-none lg:w-4/5' : 'max-w-5xl'}`}><ErrorBoundary resetKey={location.pathname + location.search}><Outlet /></ErrorBoundary></main>
    <Footer
      className="relative flex flex-wrap items-center justify-center gap-x-4 gap-y-0 space-y-0 px-gutter py-3 text-center text-xs"
      notices={<ul className="m-0 flex w-full list-none flex-wrap justify-center gap-x-2 p-0"><li>Internal evaluation app</li><li className="before:mr-2 before:content-['·']">Not official MITI coding</li></ul>}
      links={<span className="whitespace-nowrap text-footer-muted">© {new Date().getFullYear()} Onolys</span>}>
      <ThemeToggle className="absolute right-3 bottom-2" />
    </Footer>
  </div>;
}
