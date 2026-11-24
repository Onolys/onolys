import { useEffect, useMemo, useState } from 'react';
import { AuthGate } from './auth/AuthGate';
import type { AuthSession } from './auth/session';
import { createEvalApi, type RunSummary } from './api';
import { History, RunView } from './Runs';
import { getConfig } from './config';
import { NewRun } from './NewRun';
import './app.css';
import { Button } from '@onolys/ui';

const browserFetch: typeof fetch = (input, init) => fetch(input, init);
export function Root({ session, baseFetch = browserFetch }: { session: AuthSession; baseFetch?: typeof fetch }) {
  return <AuthGate session={session}><AllowedApp session={session} baseFetch={baseFetch} /></AuthGate>;
}
function AllowedApp({ session, baseFetch }: { session: AuthSession; baseFetch: typeof fetch }) {
  const api = useMemo(() => createEvalApi(getConfig().evalApiUrl, session.createFetch(baseFetch)), [session, baseFetch]);
  const [access, setAccess] = useState<'loading' | 'allowed' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [location, setLocation] = useState(() => new URL(window.location.href).searchParams);
  const [initialRun, setInitialRun] = useState<RunSummary | undefined>(() => window.history.state?.initialRun);
  const runId = location.get('run');
  const navigate = (id?: string, history = false, saved?: RunSummary) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('run'); url.searchParams.delete('view');
    if (id) url.searchParams.set('run', id);
    else if (history) url.searchParams.set('view', 'history');
    window.history.pushState(saved ? { initialRun: saved } : {}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
    setInitialRun(saved);
    setLocation(url.searchParams);
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
  return <>
      {access === 'loading' && <p role="status">Checking access…</p>}
      {access === 'error' && <div role="alert"><p>Could not reach the server.</p><Button onClick={() => { setAccess('loading'); setAttempt(n => n + 1); }}>Retry</Button></div>}
      {access === 'allowed' && <>
        {runId ? <RunView key={runId} api={api} runId={runId} onRerun={rerun} /> : location.get('view') === 'history' ? <History api={api} onOpen={navigate} onRerun={rerun} /> : <NewRun key={initialRun?.run_id ?? 'new'} api={api} initialRun={initialRun} onRunCreated={navigate} />}
      </>}
  </>;
}
