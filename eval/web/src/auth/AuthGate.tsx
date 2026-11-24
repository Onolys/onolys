import { useEffect, useState, useSyncExternalStore } from "react";
import type { FormEvent, ReactNode } from "react";
import { AppHeader, Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger, SkipLink } from '@onolys/ui';
import type { AuthSession } from "./session";

function Login({ session }: { session: AuthSession }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(false);
    try {
      await fn();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(() => session.signInWithEmail(email, password));
  };
  return (
    <div className="app-message">
      <form onSubmit={submit}>
        <h2>Sign in</h2>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        <Button type="submit" disabled={busy}>Sign in</Button>
        <Button type="button" disabled={busy} onClick={() => void run(() => session.signInWithGoogle())}>Sign in with Google</Button>
        {error ? <p role="alert">Sign-in failed. Check your details and try again.</p> : null}
      </form>
    </div>
  );
}

/** The auth gate keeps account controls available even after an access denial. */
export function AuthGate({ session, children }: { session: AuthSession; children: ReactNode }) {
  const { status, denialCode, user } = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [menuOpen, setMenuOpen] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const [query, setQuery] = useState(window.location.search);
  useEffect(() => {
    const update = () => setQuery(window.location.search);
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  const signedIn = status === 'signed-in' || status === 'forbidden';
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
      navigation={status === 'signed-in' ? <><a href={link()} onClick={navigate} aria-current={!historySelected ? 'page' : undefined}>New Run</a><a href={link(true)} onClick={navigate} aria-current={historySelected ? 'page' : undefined}>History</a></> : undefined}
      accountMenu={signedIn ? <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <Button asChild size="icon" className="rounded-full font-semibold"><DropdownMenuTrigger aria-label="Account menu">{(user?.email?.[0] ?? '?').toUpperCase()}</DropdownMenuTrigger></Button>
        <DropdownMenuContent align="end">
          {user?.email && <DropdownMenuLabel>{user.email}</DropdownMenuLabel>}
          <DropdownMenuItem onSelect={() => { setSignOutError(''); void session.signOut().catch(() => setSignOutError('Could not sign out. Please try again.')); }}>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu> : undefined} />
    {signOutError && <p role="alert">{signOutError}</p>}
    <main id="main" className="eval-main">
      {status === 'loading' ? <p role="status">Loading sign-in…</p> : status === 'signed-out' ? <Login session={session} /> : status === 'forbidden' ? <div className="app-message" role="alert"><h2>Not allowed</h2><p>{denialCode === 'email_unverified' ? 'Verify your email, then sign out and sign in again.' : denialCode === 'not_allowlisted' ? 'This account is not on the app access list. Contact an administrator.' : 'This account is not allowed to use this app, or its email is not verified.'}</p></div> : children}
    </main>
  </div>;
}
