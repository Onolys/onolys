import { useEffect, useMemo, useState } from 'react';
import { AuthGate } from './auth/AuthGate';
import type { AuthSession } from './auth/session';
import { createEvalApi } from './api';
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
  const [runId, setRunId] = useState<string>();
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
      {access === 'allowed' && (runId ? <section><h1>Run created</h1><p role="status">Your run has started.</p><p>Run {runId}</p><button onClick={() => setRunId(undefined)}>New run</button></section> : <NewRun api={api} onRunCreated={setRunId} />)}
    </main>
  </div>;
}
