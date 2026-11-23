import { useEffect, useMemo, useState } from 'react';
import { AuthGate } from './auth/AuthGate';
import type { AuthSession } from './auth/session';
import { createEvalApi, type RunSummary } from './api';
import { History, RunView } from './Runs';
import { getConfig } from './config';
import { NewRun } from './NewRun';
import './app.css';

const browserFetch: typeof fetch = (input, init) => fetch(input, init);
export function Root({ session, baseFetch = browserFetch }: { session: AuthSession; baseFetch?: typeof fetch }) {
  return <AuthGate session={session}><AllowedApp session={session} baseFetch={baseFetch} /></AuthGate>;
}
function AllowedApp({ session, baseFetch }: { session: AuthSession; baseFetch: typeof fetch }) {
  const api = useMemo(() => createEvalApi(getConfig().evalApiUrl, session.createFetch(baseFetch)), [session, baseFetch]);
  const [access, setAccess] = useState<'loading' | 'allowed' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [location, setLocation] = useState(() => new URL(window.location.href).searchParams);
  const [initialRun, setInitialRun] = useState<RunSummary>();
  const runId = location.get('run');
  const navigate = (id?: string, history = false) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('run'); url.searchParams.delete('view');
    if (id) url.searchParams.set('run', id);
    else if (history) url.searchParams.set('view', 'history');
    window.history.pushState({}, '', url);
    setLocation(url.searchParams);
  };
  const rerun = (run: RunSummary) => { setInitialRun(run); navigate(); };
  useEffect(() => {
    const update = () => { setInitialRun(undefined); setLocation(new URL(window.location.href).searchParams); };
    window.addEventListener('popstate', update);
    return () => window.removeEventListener('popstate', update);
  }, []);
  useEffect(() => {
    let active = true;
    api.me().then(() => { if (active) setAccess('allowed'); }).catch(() => { if (active) setAccess('error'); });
    return () => { active = false; };
  }, [api, attempt]);
  return <div className="shell">
    <header><p className="eyebrow">Onolys · Evaluation</p><p>MITI 4.2.1 coding comparison</p></header>
    <main>
      {access === 'loading' && <p role="status">Checking access…</p>}
      {access === 'error' && <div role="alert"><p>Could not reach the server.</p><button onClick={() => { setAccess('loading'); setAttempt(n => n + 1); }}>Retry</button></div>}
      {access === 'allowed' && <>
        <nav aria-label="Evaluation"><button onClick={() => { setInitialRun(undefined); navigate(); }}>New run</button><button onClick={() => navigate(undefined, true)}>History</button></nav>
        {runId ? <RunView key={runId} api={api} runId={runId} onRerun={rerun} /> : location.get('view') === 'history' ? <History api={api} onOpen={navigate} onRerun={rerun} /> : <NewRun key={initialRun?.run_id ?? 'new'} api={api} initialRun={initialRun} onRunCreated={navigate} />}
      </>}
    </main>
  </div>;
}
