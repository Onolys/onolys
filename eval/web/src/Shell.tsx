import { useEffect, useState } from 'react';
import { Outlet } from 'react-router';
import { AppHeader, Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger, SkipLink } from '@onolys/ui';
import { useAuth } from '@prod-auth/AuthProvider';
import { useSignOut } from '@prod-auth/useSignOut';

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
  const link = (history = false) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('run'); url.searchParams.delete('view');
    if (history) url.searchParams.set('view', 'history');
    return url.pathname + url.search + url.hash;
  };
  const historySelected = new URLSearchParams(query).get('view') === 'history' || new URLSearchParams(query).has('run');
  return <div className="shell">
    <SkipLink />
    <AppHeader brand={<a className="font-bold text-primary no-underline" href={link()} onClick={navigate}>Onolys <span className="text-sm font-normal">Evaluation</span></a>}
      navigation={phase === 'verified' ? <><a href={link()} onClick={navigate} aria-current={!historySelected ? 'page' : undefined}>New Run</a><a href={link(true)} onClick={navigate} aria-current={historySelected ? 'page' : undefined}>History</a></> : undefined}
      accountMenu={signedIn ? <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <Button asChild size="icon" className="rounded-full font-semibold"><DropdownMenuTrigger aria-label="Account menu">{(user?.email?.[0] ?? '?').toUpperCase()}</DropdownMenuTrigger></Button>
        <DropdownMenuContent align="end">
          {user?.email && <DropdownMenuLabel>{user.email}</DropdownMenuLabel>}
          <DropdownMenuItem onSelect={() => void signOut()}>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu> : undefined} />
    {error && <p role="alert">{error}</p>}
    <main id="main" className="eval-main"><Outlet /></main>
  </div>;
}
