import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router';
import { AccountMenu, AppHeader, Footer, NAV_LINK, SkipLink, ThemeToggle } from '@onolys/common';
import { useAuth, useSignOut } from '@onolys/common/auth';
import { ErrorBoundary } from './ErrorPage';

/** Eval page chrome: header, nav and account menu around the routed content. */
export function Shell() {
  const { phase, user } = useAuth();
  const { signOut, error } = useSignOut();
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
      // signed in: page tabs sit at the true centre of the bar (brand left, account menu right)
      centerNavigation={phase === 'verified'}
      brand={<a className="font-bold text-primary no-underline" href={link()} onClick={navigate}>Onolys<span className="ml-2 text-sm font-normal text-muted-foreground">Evaluation</span></a>}
      navigation={phase === 'verified' ? <><a className={NAV_LINK} href={link()} onClick={navigate} aria-current={!historySelected ? 'page' : undefined}>New Run</a><a className={NAV_LINK} href={link(true)} onClick={navigate} aria-current={historySelected ? 'page' : undefined}>History</a></> : undefined}
      accountMenu={signedIn ? <AccountMenu email={user?.email ?? null} onSignOut={() => void signOut()} /> : undefined} />
    {error && <p role="alert">{error}</p>}
    {/* signed-out pages (login) use the standard page width; the signed-in app uses the wide-page width */}
    <main id="main" className={`eval-main mx-auto w-full flex-1 px-4 py-6 ${signedIn ? 'max-w-none lg:w-4/5' : 'max-w-5xl'}`}><ErrorBoundary resetKey={location.pathname + location.search}><Outlet /></ErrorBoundary></main>
    <Footer
      compact
      notices={<ul className="m-0 flex w-full list-none flex-wrap justify-center gap-x-2 p-0"><li>Internal evaluation app</li><li className="before:mr-2 before:content-['·']">Not official MITI coding</li></ul>}
      links={<span className="whitespace-nowrap text-footer-muted">© {new Date().getFullYear()} Onolys</span>}
      themeToggle={<ThemeToggle />} />
  </div>;
}
