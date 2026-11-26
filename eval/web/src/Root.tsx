// Must load before every other stylesheet: it declares the cascade layer order (theme, base, components, utilities).
import './app.css';
import { useEffect, useMemo, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@prod-auth/AuthProvider';
import { PublicOnly, RequireUnverified, RequireVerified } from '@prod-auth/guards';
import { Login } from '@prod-auth/pages/Login';
import type { AuthService } from '@prod-auth/types';
import { createEvalApi, type RunSummary } from './api';
import { parseCompareUrl } from './compare/compareUrl';
import { navigateEval } from './evalNavigation';
import { History, RunView } from './Runs';
import { CompareApp } from './compare/CompareApp';
import { getConfig } from './config';
import { NewRun } from './NewRun';
import { ColdStartNotice } from './ColdStart';
import { ErrorBoundary, ErrorPage } from './ErrorPage';
import { NoAccess } from './NoAccess';
import { Shell } from './Shell';
import { createAuthFetch } from './transport/authFetch';
import { Button } from '@onolys/ui';

export { navigateEval } from './evalNavigation';
const browserFetch: typeof fetch = (input, init) => fetch(input, init);
export function Root({ service, baseFetch = browserFetch }: { service: AuthService; baseFetch?: typeof fetch }) {
  const [queryClient] = useState(() => new QueryClient());
  return <ErrorBoundary standalone><QueryClientProvider client={queryClient}><AuthProvider service={service}><BrowserRouter><Routes>
    <Route element={<Shell />}>
      <Route element={<PublicOnly />}><Route path="/login" element={<Login showSignup={false} showForgot={false} showGoogle={false} note="Ask the Onolys team for an eval account." />} /></Route>
      <Route element={<RequireUnverified />}><Route path="/verify-email" element={<EvalUnverified />} /></Route>
      <Route element={<RequireVerified />}><Route path="/" element={<AllowedApp baseFetch={baseFetch} />} /><Route path="*" element={<ErrorPage notFound />} /></Route>
    </Route>
  </Routes></BrowserRouter></AuthProvider></QueryClientProvider></ErrorBoundary>;
}
/** Unverified accounts cannot self-verify on eval (no emails): the old /verify-email redirect target would loop. */
function EvalUnverified() {
  const { signOut } = useAuth();
  return <div className="app-message" role="alert">
    <h2>Account not verified</h2>
    <p>Your eval account isn't verified. Ask the Onolys team.</p>
    <Button type="button" onClick={() => void signOut()}>Sign out</Button>
  </div>;
}
function AllowedApp({ baseFetch }: { baseFetch: typeof fetch }) {
  const { service, signOut } = useAuth();
  const [denied, setDenied] = useState<{ code?: string } | null>(null);
  const api = useMemo(() => createEvalApi(getConfig().evalApiUrl, createAuthFetch({
    fetch: baseFetch,
    getToken: force => service.getToken(force),
    onUnauthorized: () => void signOut().catch(() => undefined),
    onForbidden: code => setDenied({ code }),
  })), [service, signOut, baseFetch]);
  const [access, setAccess] = useState<'loading' | 'allowed' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [location, setLocation] = useState(() => new URL(window.location.href).searchParams);
  const [initialRun, setInitialRun] = useState<RunSummary | undefined>(() => window.history.state?.initialRun);
  const runId = location.get('run');
  const navigate = (id?: string, history = false, saved?: RunSummary) => {
    navigateEval({run:id,view:id ? 'run' : history ? 'history' : 'new'}, saved);
  };
  const rerun = (run: RunSummary) => navigate(undefined, false, run);
  useEffect(() => {
    const update = () => { setInitialRun(window.history.state?.initialRun); setLocation(new URL(window.location.href).searchParams); };
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  useEffect(() => {
    let active = true;
    api.me().then(() => { if (active) setAccess('allowed'); }).catch(() => { if (active) setAccess('error'); });
    return () => { active = false; };
  }, [api, attempt]);
  if (denied) return <NoAccess code={denied.code} />;
  return <>
      {access === 'loading' && <><p role="status">Checking access…</p><ColdStartNotice pending /></>}
      {access === 'error' && <div role="alert"><p>Could not reach the server.</p><Button onClick={() => { setAccess('loading'); setAttempt(n => n + 1); }}>Retry</Button></div>}
      {access === 'allowed' && <>
        {runId && location.get('view') === 'compare' ? <CompareApp key={runId} api={api} runId={runId} state={parseCompareUrl(location)} navigate={navigateEval} /> : runId ? <RunView key={runId} api={api} runId={runId} onRerun={rerun} /> : location.get('view') === 'history' ? <History api={api} onOpen={navigate} onRerun={rerun} /> : <NewRun key={initialRun?.run_id ?? 'new'} api={api} initialRun={initialRun} onRunCreated={navigate} />}
      </>}
  </>;
}
