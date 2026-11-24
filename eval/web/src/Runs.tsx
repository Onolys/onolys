import { useEffect, useRef, useState } from 'react';
import type { Compare, CompareAggregate, ErrorMetric, EvalApi, RunDetail, RunSummary, RunUnit } from './api';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not load run. Please try again.';
const terminal = (status: string) => !['queued', 'running'].includes(status);
const number = (value: number | null | undefined, metric = '') => value == null ? '—' : metric === 'pct_cr' ? `${Number((value * 100).toFixed(2))}%` : String(Number(value.toFixed(3)));
const statusLabel = (run: RunSummary, cancelRequested = false) => cancelRequested && !terminal(run.status) ? 'cancelling' : run.status;
const dateText = (iso: string) => { const date = new Date(iso); return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(); };
const HISTORY_LIMIT = 100; // the server returns at most this many runs, newest first
const POLL_MS = 3000, MAX_POLL_MS = 30000;
const inputName = (run: RunSummary) => 'dataset_id' in run.input ? run.input.dataset_id : run.input.upload_id;

function Usage({ run }: { run: RunSummary }) {
  return <p>{run.usage.input_tokens} input tokens · {run.usage.output_tokens} output tokens · {run.cost_usd_est == null ? '—' : `~$${run.cost_usd_est.toFixed(4)}`} estimate; STT excluded.{run.unpriced_units > 0 && ` ${run.unpriced_units} unpriced unit(s); estimate is incomplete.`}</p>;
}
function Provenance({ run }: { run: RunSummary }) {
  return <details><summary>Saved configuration and versions</summary><pre>{JSON.stringify({ input: run.input, change_goal: run.change_goal, language: run.language, coded_span: run.coded_span, engines: run.engines, presets: run.presets, repeats: run.repeats, engine_versions: run.engine_versions, engine_git_sha: run.engine_git_sha, base_preset: run.base_preset, resolved_combos: run.resolved_combos, resolved_presets: run.resolved_presets }, null, 2)}</pre></details>;
}
const sortValue = (a: CompareAggregate, key: string): number | string | null => {
  if (key === 'label') return `${a.engine} · ${a.label}`;
  if (key === 'n') return a.n;
  if (key === 'failed') return a.failed;
  if (key === 'tokens') return a.usage.input_tokens + a.usage.output_tokens;
  if (key === 'cost') return a.cost_usd_est;
  if (key.startsWith('w1:')) return a.within_1[key.slice(3)]?.fraction ?? null;
  const [group, id] = key.split(':'); return (a.metrics[group as 'counts'] as Record<string, ErrorMetric> | undefined)?.[id]?.mae ?? null;
};
export function SummaryView({ compare }: { compare: Compare }) {
  const [sort, setSort] = useState<{ key: string; dir: 'ascending' | 'descending' } | null>(null);
  const globals = compare.metrics.filter(m => m.group === 'globals');
  const columns = [...compare.metrics.map(m => ({ key: `${m.group}:${m.id}`, label: `MAE ${m.label}`, mae: true })), ...globals.map(m => ({ key: `w1:${m.id}`, label: `Within 1 ${m.label}`, mae: false })),
    { key: 'n', label: 'n sessions', mae: false }, { key: 'failed', label: 'Failed units', mae: false }, { key: 'tokens', label: 'Tokens', mae: false }, { key: 'cost', label: 'Est. cost', mae: false }];
  const best: Record<string, number | undefined> = {};
  for (const c of columns.filter(c => c.mae)) { const v = compare.aggregates.map(a => sortValue(a, c.key)).filter((x): x is number => typeof x === 'number'); if (v.length) best[c.key] = Math.min(...v); }
  const rows = [...compare.aggregates];
  if (sort) rows.sort((x, y) => {
    const a = sortValue(x, sort.key), b = sortValue(y, sort.key);
    if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
    const c = typeof a === 'string' ? a.localeCompare(b as string) : a - (b as number);
    return sort.dir === 'ascending' ? c : -c;
  });
  const toggle = (key: string) => setSort(s => s?.key === key ? { key, dir: s.dir === 'ascending' ? 'descending' : 'ascending' } : { key, dir: 'ascending' });
  const head = (key: string, label: string) => <th scope="col" key={key} aria-sort={sort?.key === key ? sort.dir : 'none'}><button type="button" className="sort" onClick={() => toggle(key)}>{label}</button></th>;
  const cost = (v: number | null) => v == null ? '—' : `$${v.toFixed(4)}`;
  return <div className="table-scroll"><table className="matrix"><caption>Mean absolute error (MAE) per engine and combo, over successful units; lower is better and the best value per column is highlighted. Within 1 is the share of global ratings within one point of Human.</caption>
    <thead><tr>{head('label', 'Engine / combo')}{columns.map(c => head(c.key, c.label))}</tr></thead>
    <tbody>{rows.map(a => <tr key={`${a.engine}/${a.combo_key}`}><th scope="row">{a.engine} · {a.label}</th>
      {columns.map(c => {
        const v = sortValue(a, c.key); const isBest = c.mae && typeof v === 'number' && v === best[c.key];
        const text = c.key.startsWith('w1:') ? (a.within_1[c.key.slice(3)]?.fraction == null ? '—' : String(Number(a.within_1[c.key.slice(3)].fraction!.toFixed(3)))) : c.key === 'cost' ? cost(a.cost_usd_est) : c.mae ? number(v as number | null, c.key.split(':')[1]) : String(v);
        return <td key={c.key} className={isBest ? 'best' : undefined} data-best={isBest ? 'true' : undefined}>{text}{isBest && <span className="sr-only"> (best)</span>}</td>;
      })}</tr>)}</tbody></table></div>;
}
export function CompareView({ compare }: { compare: Compare }) {
  const [sessionId, setSessionId] = useState(compare.sessions[0]?.session_id ?? '');
  const [tab, setTab] = useState<'compare' | 'summary'>('compare');
  const session = compare.sessions.find(s => s.session_id === sessionId) ?? compare.sessions[0];
  if (!session) return <p>Comparison will appear when units are available.</p>;
  const showSummary = compare.has_human && tab === 'summary';
  return <section><h2>Compare</h2>
    {compare.has_human && <div role="tablist" aria-label="Results view"><button type="button" role="tab" aria-selected={!showSummary} onClick={() => setTab('compare')}>Compare</button><button type="button" role="tab" aria-selected={showSummary} onClick={() => setTab('summary')}>Summary</button></div>}
    {showSummary ? <SummaryView compare={compare} /> : <>
    <label>Session<select value={session.session_id} onChange={event => setSessionId(event.target.value)}>{compare.sessions.map(s => <option key={s.session_id} value={s.session_id}>{s.session_id}</option>)}</select></label>
    <div className="table-scroll"><table className="matrix"><caption>Successful unit means and min–max ranges; n counts defined values.{compare.has_human && ' Beneath each value: signed diff vs Human and session MAE over successful units.'} Failed units are excluded from values{compare.has_human ? ' and MAE' : ''}.</caption>
      <thead><tr><th scope="col">Engine / combo</th>{compare.metrics.map(m => <th scope="col" key={m.id}>{m.label}</th>)}</tr></thead>
      <tbody>
        {compare.has_human && <tr><th scope="row">Human</th>{compare.metrics.map(m => <td key={m.id}>{session.human?.[m.id] == null ? '—, n=0' : `${number(session.human[m.id], m.id)}, n=1`}</td>)}</tr>}
        {session.cells.map(cell => <tr key={`${cell.engine}/${cell.combo_key}`}><th scope="row">{cell.engine} · {cell.label}{cell.failed > 0 && <span role="status" className="failed"> {cell.failed} failed{cell.error_code ? ` (${cell.error_code})` : ''}</span>}</th>
          {compare.metrics.map(m => { const value = cell.values[m.id]; const err = cell.error?.[m.id];
            return <td key={m.id}>{value?.mean == null ? `—, n=${value?.n ?? 0}` : `${number(value.mean, m.id)} (${number(value.min, m.id)}–${number(value.max, m.id)}), n=${value.n}`}
              {compare.has_human && cell.diff && <small className="sub"> diff {number(cell.diff[m.id], m.id)}</small>}
              {compare.has_human && err && <small className="sub"> MAE {number(err.mae, m.id)}</small>}</td>; })}
        </tr>)}
      </tbody></table></div></>}
    {compare.notes.map((note, index) => <p key={index}>{note}</p>)}
  </section>;
}
function UnitOutput({ api, runId, unit }: { api: EvalApi; runId: string; unit: RunUnit }) {
  const [open, setOpen] = useState(false);
  const [output, setOutput] = useState<unknown>(unit.output);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open || output !== undefined) return;
    const controller = new AbortController();
    api.output(runId, unit.unit_id, controller.signal).then(value => { if (!controller.signal.aborted) setOutput(value); }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => controller.abort();
  }, [api, runId, unit.unit_id, open, output, attempt]);
  return <><button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide' : 'View'} JSON {unit.unit_id}</button>{open && (error ? <div role="alert">{error}<button onClick={() => { setError(''); setAttempt(n => n + 1); }}>Retry JSON</button></div> : output === undefined ? <p role="status">Loading JSON…</p> : <pre>{JSON.stringify(output, null, 2)}</pre>)}</>;
}
export function RunView({ api, runId, onRerun }: { api: EvalApi; runId: string; onRerun: (run: RunSummary) => void }) {
  const [run, setRun] = useState<RunDetail>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const stop = useRef<() => void>(() => {});
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const halt = () => { clearTimeout(timer); controller.abort(); };
    stop.current = halt;
    let failures = 0;
    const poll = async () => {
      try {
        const value = await api.run(runId, controller.signal);
        if (controller.signal.aborted) return;
        failures = 0; setError('');
        setRun(value);
        if (!terminal(value.status)) timer = setTimeout(() => void poll(), POLL_MS);
      } catch (e) {
        if (controller.signal.aborted) return;
        failures += 1; setError(errorMessage(e));
        timer = setTimeout(() => void poll(), Math.min(POLL_MS * 2 ** (failures - 1), MAX_POLL_MS));
      }
    };
    void poll(); return halt;
  }, [api, runId, attempt]);
  const cancel = async () => {
    if (cancelling) return;
    setCancelling(true); setError('');
    try {
      await api.cancel(runId);
      stop.current();
      setAttempt(n => n + 1);
    } catch (e) { setError(errorMessage(e)); setCancelling(false); }
  };
  const cancelRequested = cancelling || run?.cancel_requested === true;
  return <section><h1>Run {runId}</h1>{error && <div role="alert">{error}{run && !terminal(run.status) && ' Still trying to refresh.'}<button onClick={() => { setError(''); setAttempt(n => n + 1); }}>Retry run status</button></div>}
    {!run ? <p role="status">Loading run…</p> : <>
      <p role="status">{statusLabel(run, cancelRequested)} · {run.completed_units}/{run.total_units} units complete · {run.failed_units} failed · {run.cancelled_units} cancelled</p>
      {!terminal(run.status) && <button disabled={cancelRequested} onClick={() => void cancel()}>{cancelRequested ? 'Cancelling…' : 'Cancel run'}</button>}
      <button onClick={() => onRerun(run)}>Rerun with different engines/presets</button>
      <Usage run={run} /><Provenance run={run} />
      <h2>Unit progress and repeats</h2><div className="unit-grid">{run.units.map(unit => <article className="unit" key={unit.unit_id}><h3>{unit.session_id} · {unit.engine}{unit.preset ? ` · ${unit.preset}` : ''}</h3><p>{unit.repeat != null && `Repeat ${unit.repeat + 1} · `}{unit.status}{unit.stage ? ` · ${unit.stage}` : ''}</p>{unit.error && <p role="alert">{typeof unit.error === 'string' ? unit.error : `${unit.error.code}${unit.error.message ? `: ${unit.error.message}` : ''}`}</p>}{unit.status === 'done' && <UnitOutput api={api} runId={runId} unit={unit} />}</article>)}</div>
      <CompareView compare={run.compare} />
    </>}
  </section>;
}
export function History({ api, onOpen, onRerun }: { api: EvalApi; onOpen: (id: string) => void; onRerun: (run: RunSummary) => void }) {
  const [runs, setRuns] = useState<RunSummary[]>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.runs(controller.signal).then(value => { if (!controller.signal.aborted) setRuns(value.runs); }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)); });
    return () => controller.abort();
  }, [api, attempt]);
  return <section><h1>History</h1>{runs && runs.length >= HISTORY_LIMIT && <p role="note">Showing the latest {HISTORY_LIMIT} runs. Older runs are not listed.</p>}{error && <div role="alert">{error}<button onClick={() => { setError(''); setAttempt(n => n + 1); }}>Retry history</button></div>}{!runs ? <p role="status">Loading history…</p> : runs.length === 0 ? <p>No saved runs yet.</p> : <div className="table-scroll"><table><thead><tr>{['Date', 'Input', 'Engines / presets', 'Status', 'Tokens / estimated cost', 'Details'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{runs.map(run => <tr key={run.run_id}><td><time dateTime={run.created_at}>{dateText(run.created_at)}</time></td><td>{inputName(run)}</td><td>{run.engines.join(', ')} / {(run.combo_keys ?? run.presets ?? []).join(', ')} · {run.repeats} runs per cell</td><td>{statusLabel(run, run.cancel_requested === true)}</td><td><Usage run={run} /></td><td><button onClick={() => onOpen(run.run_id)}>Open run {run.run_id}</button><button onClick={() => onRerun(run)}>Rerun with different engines/presets</button><Provenance run={run} /></td></tr>)}</tbody></table></div>}</section>;
}
