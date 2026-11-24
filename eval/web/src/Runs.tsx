import { useEffect, useRef, useState } from 'react';
import type { Compare, EvalApi, RunDetail, RunSummary, RunUnit } from './api';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not load run. Please try again.';
const terminal = (status: string) => !['queued', 'running'].includes(status);
const number = (value: number | null | undefined, metric = '') => value == null ? '—' : metric === 'pct_cr' ? `${Number((value * 100).toFixed(2))}%` : String(Number(value.toFixed(3)));
const inputName = (run: RunSummary) => 'dataset_id' in run.input ? run.input.dataset_id : run.input.upload_id;

function Usage({ run }: { run: RunSummary }) {
  return <p>{run.usage.input_tokens} input tokens · {run.usage.output_tokens} output tokens · {run.cost_usd_est == null ? '—' : `~$${run.cost_usd_est.toFixed(4)}`} estimate; STT excluded.{run.unpriced_units > 0 && ` ${run.unpriced_units} unpriced unit(s); estimate is incomplete.`}</p>;
}
function Provenance({ run }: { run: RunSummary }) {
  return <details><summary>Saved configuration and versions</summary><pre>{JSON.stringify({ input: run.input, change_goal: run.change_goal, language: run.language, coded_span: run.coded_span, engines: run.engines, presets: run.presets, repeats: run.repeats, engine_versions: run.engine_versions, engine_git_sha: run.engine_git_sha, resolved_presets: run.resolved_presets }, null, 2)}</pre></details>;
}
export function CompareView({ compare }: { compare: Compare }) {
  const [sessionId, setSessionId] = useState(compare.sessions[0]?.session_id ?? '');
  const session = compare.sessions.find(s => s.session_id === sessionId) ?? compare.sessions[0];
  if (!session) return <p>Comparison will appear when units are available.</p>;
  return <section><h2>Compare</h2>
    <label>Session<select value={session.session_id} onChange={event => setSessionId(event.target.value)}>{compare.sessions.map(s => <option key={s.session_id} value={s.session_id}>{s.session_id}</option>)}</select></label>
    {session.cells.map(cell => cell.failed > 0 && <p key={`${cell.engine}/${cell.preset}`} role="status">{cell.engine} · {cell.preset}: {cell.failed} failed unit(s), excluded from values{compare.has_human ? ' and MAE' : ''}.</p>)}
    <div className="table-scroll"><table><caption>Successful unit means and min–max ranges; n counts defined values.{compare.has_human && ' MAE over successful run units across sessions and repeats; n counts defined unit comparisons.'}</caption>
      <thead><tr><th scope="col">Metric</th>{compare.has_human && <th scope="col">Human</th>}{session.cells.map(cell => <th scope="col" key={`${cell.engine}/${cell.preset}`}>{cell.engine} · {cell.preset}</th>)}{compare.has_human && session.cells.map(cell => <th scope="col" key={`diff/${cell.engine}/${cell.preset}`}>Diff vs Human · {cell.engine} · {cell.preset}</th>)}{compare.has_human && session.cells.map(cell => <th scope="col" key={`mae/${cell.engine}/${cell.preset}`}>MAE · {cell.engine} · {cell.preset}</th>)}</tr></thead>
      <tbody>{compare.metrics.map(metric => <tr key={metric.id}><th scope="row">{metric.label}</th>
        {compare.has_human && <td>{session.human?.[metric.id] == null ? '—, n=0' : `${number(session.human[metric.id], metric.id)}, n=1`}</td>}
        {session.cells.map(cell => { const value = cell.values[metric.id]; return <td key={`${cell.engine}/${cell.preset}`}>{value?.mean == null ? `—, n=${value?.n ?? 0}` : `${number(value.mean, metric.id)} (${number(value.min, metric.id)}–${number(value.max, metric.id)}), n=${value.n}`}</td>; })}
        {compare.has_human && session.cells.map(cell => <td key={`diff/${cell.engine}/${cell.preset}`}>{number(cell.diff?.[metric.id], metric.id)}</td>)}
        {compare.has_human && session.cells.map(cell => { const aggregate = compare.aggregates.find(a => a.engine === cell.engine && a.preset === cell.preset); const value = aggregate?.metrics[metric.group][metric.id]; return <td key={`mae/${cell.engine}/${cell.preset}`}>{number(value?.mae, metric.id)}, n={value?.n ?? 0}</td>; })}
      </tr>)}</tbody></table></div>
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
    const poll = async () => {
      try {
        const value = await api.run(runId, controller.signal);
        if (controller.signal.aborted) return;
        setRun(value);
        if (!terminal(value.status)) timer = setTimeout(() => void poll(), 3000);
      } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
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
  return <section><h1>Run {runId}</h1>{error && <div role="alert">{error}<button onClick={() => { setError(''); setAttempt(n => n + 1); }}>Retry run status</button></div>}
    {!run ? <p role="status">Loading run…</p> : <>
      <p role="status">{run.status} · {run.completed_units}/{run.total_units} units complete · {run.failed_units} failed · {run.cancelled_units} cancelled</p>
      {!terminal(run.status) && <button disabled={cancelling} onClick={() => void cancel()}>{cancelling ? 'Cancelling…' : 'Cancel run'}</button>}
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
  return <section><h1>History</h1>{error && <div role="alert">{error}<button onClick={() => { setError(''); setAttempt(n => n + 1); }}>Retry history</button></div>}{!runs ? <p role="status">Loading history…</p> : runs.length === 0 ? <p>No saved runs yet.</p> : <div className="table-scroll"><table><thead><tr>{['Date', 'Input', 'Engines / presets', 'Status', 'Tokens / estimated cost', 'Details'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{runs.map(run => <tr key={run.run_id}><td><time dateTime={run.created_at}>{run.created_at}</time></td><td>{inputName(run)}</td><td>{run.engines.join(', ')} / {(run.combo_keys ?? run.presets ?? []).join(', ')} · {run.repeats} runs per cell</td><td>{run.status}</td><td><Usage run={run} /></td><td><button onClick={() => onOpen(run.run_id)}>Open run {run.run_id}</button><button onClick={() => onRerun(run)}>Rerun with different engines/presets</button><Provenance run={run} /></td></tr>)}</tbody></table></div>}</section>;
}
