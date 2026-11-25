import { useEffect, useId, useRef, useState } from 'react';
import { Badge, Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Input } from '@onolys/ui';
import { ApiError } from './api';
import { RunConfigDialog, savedConfiguration } from './RunConfigDialog';
import './runs.css';
import type { Compare, CompareAggregate, ErrorMetric, EvalApi, RunDetail, RunSummary, RunUnit } from './api';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not load run. Please try again.';
const terminal = (status: string) => !['queued', 'running'].includes(status);
const deletable = (status: string) => ['done', 'partial', 'failed', 'cancelled'].includes(status);
const number = (value: number | null | undefined, metric = '') => value == null ? '—' : metric === 'pct_cr' ? `${Number((value * 100).toFixed(2))}%` : String(Number(value.toFixed(3)));
const statusLabel = (run: RunSummary, cancelRequested = false) => cancelRequested && !terminal(run.status) ? 'cancelling' : run.status;
const dateText = (iso: string) => { const date = new Date(iso); return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(); };
const localDate = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const POLL_MS = 3000, MAX_POLL_MS = 30000;
const inputName = (run: RunSummary) => 'dataset_id' in run.input ? run.input.dataset_id : run.input.upload_id;

function Usage({ run }: { run: RunSummary }) {
  return <p>{run.usage.input_tokens} input tokens · {run.usage.output_tokens} output tokens · {run.cost_usd_est == null ? '—' : `~$${run.cost_usd_est.toFixed(4)}`} estimate; STT excluded.{run.unpriced_units > 0 && ` ${run.unpriced_units} unpriced unit(s); estimate is incomplete.`}</p>;
}
function RunActions({ run, onRerun, onConfig, onDelete }: { run: RunSummary; onRerun: (run: RunSummary) => void; onDelete: (run: RunSummary) => void; onConfig: (run: RunSummary, trigger: HTMLElement | null) => void }) {
  const trigger = useRef<HTMLButtonElement>(null);
  const openingConfig = useRef(false);
  return <DropdownMenu><DropdownMenuTrigger asChild><Button ref={trigger} variant="ghost" size="icon" aria-label={`Actions for ${run.name || inputName(run)}`}>⋮</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" onCloseAutoFocus={event => {
      if (openingConfig.current) { event.preventDefault(); openingConfig.current = false; }
    }}><DropdownMenuItem onSelect={() => onRerun(run)}>Rerun</DropdownMenuItem><DropdownMenuItem onSelect={() => { openingConfig.current = true; onConfig(run, trigger.current); }}>Config</DropdownMenuItem><DropdownMenuItem disabled={!deletable(run.status)} onSelect={() => onDelete(run)}>Delete</DropdownMenuItem></DropdownMenuContent>
  </DropdownMenu>;
}
const historyColumns = ['Date', 'Dataset', 'Status', 'Engines', 'Models', 'Tiers', 'Efforts'] as const;
type HistoryColumn = typeof historyColumns[number];
function comboFields(run: RunSummary, preset?: string | null) {
  const index = preset ? run.combo_keys?.indexOf(preset) : -1;
  const combo = index >= 0 ? run.combos?.[index] : undefined;
  const resolved = (preset ? run.resolved_combos?.[preset] ?? run.resolved_presets?.[preset.replace(/^preset:/, '')] : undefined) as Record<string, unknown> | undefined;
  const string = (value: unknown) => typeof value === 'string' ? value : '';
  const legacyModels = preset && run.presets?.includes(preset.replace(/^preset:/, '')) ? [...new Set(Object.values(resolved ?? {}).filter(value => typeof value === 'string'))].join(', ') : '';
  return {
    model: combo?.model || string(resolved?.model) || string(resolved?.litellm_id) || legacyModels,
    tier: combo?.tier || string(resolved?.tier),
    effort: combo?.effort || string(resolved?.effort) || string(resolved?.reasoning_effort),
  };
}
function columnValue(run: RunSummary, column: HistoryColumn): string {
  const selected = (key: 'models' | 'tiers' | 'efforts', field: 'model' | 'tier' | 'effort') => {
    const values = [...(run.selection?.[key] ?? []), ...(run.combos ?? []).map(combo => combo[field]),
      ...[...(run.combo_keys ?? []), ...(run.presets ?? [])].map(preset => comboFields(run, preset)[field])].filter(Boolean);
    return [...new Set(values)].join(', ') || '—';
  };
  switch (column) {
    case 'Date': return dateText(run.created_at);
    case 'Dataset': return inputName(run);
    case 'Status': return statusLabel(run, run.cancel_requested);
    case 'Engines': return run.engines.join(', ');
    case 'Models': return selected('models', 'model');
    case 'Tiers': return selected('tiers', 'tier');
    case 'Efforts': return selected('efforts', 'effort');
  }
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
  const showQuality = compare.sessions.some(s => s.quality_label != null);
  return <section><h2>Compare</h2>
    {compare.has_human && <div role="tablist" aria-label="Results view"><button type="button" role="tab" aria-selected={!showSummary} onClick={() => setTab('compare')}>Compare</button><button type="button" role="tab" aria-selected={showSummary} onClick={() => setTab('summary')}>Summary</button></div>}
    {showSummary ? <SummaryView compare={compare} /> : <>
    <label>Session<select value={session.session_id} onChange={event => setSessionId(event.target.value)}>{compare.sessions.map(s => <option key={s.session_id} value={s.session_id}>{s.session_id}</option>)}</select></label>
    <div className="table-scroll"><table className="matrix"><caption>Successful unit means and min–max ranges; n counts defined values.{compare.has_human && ' Beneath each value: signed diff vs Human and session MAE over successful units.'} Failed units are excluded from values{compare.has_human ? ' and MAE' : ''}.</caption>
      <thead><tr><th scope="col">Engine / combo</th>{compare.metrics.map(m => <th scope="col" key={m.id}>{m.label}</th>)}{showQuality && <th scope="col">Quality label</th>}</tr></thead>
      <tbody>
        {compare.has_human && <tr><th scope="row">Human</th>{compare.metrics.map(m => <td key={m.id}>{session.human?.[m.id] == null ? '—, n=0' : `${number(session.human[m.id], m.id)}, n=1`}</td>)}{showQuality && <td>{session.quality_label ?? '—'}</td>}</tr>}
        {session.cells.map(cell => <tr key={`${cell.engine}/${cell.combo_key}`}><th scope="row">{cell.engine} · {cell.label}{cell.failed > 0 && <span role="status" className="failed"> {cell.failed} failed{cell.error_code ? ` (${cell.error_code})` : ''}</span>}</th>
          {compare.metrics.map(m => { const value = cell.values[m.id]; const err = cell.error?.[m.id];
            return <td key={m.id}>{value?.mean == null ? `—, n=${value?.n ?? 0}` : `${number(value.mean, m.id)} (${number(value.min, m.id)}–${number(value.max, m.id)}), n=${value.n}`}
              {compare.has_human && cell.diff && <small className="sub"> diff {number(cell.diff[m.id], m.id)}</small>}
              {compare.has_human && err && <small className="sub"> MAE {number(err.mae, m.id)}</small>}</td>; })}
          {showQuality && <td>{session.quality_label ?? '—'}</td>}
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
  const [missing, setMissing] = useState(false);
  const [configuration, setConfiguration] = useState<RunSummary | null>(null);
  const configTrigger = useRef<HTMLElement | null>(null);
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
        failures = 0; setError(''); setMissing(false);
        setRun(value);
        if (!terminal(value.status)) timer = setTimeout(() => void poll(), POLL_MS);
      } catch (e) {
        if (controller.signal.aborted) return;
        failures += 1; setError(errorMessage(e));
        if (e instanceof ApiError && e.status === 404) { setMissing(true); return; }
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
  return <section className="run-detail"><h1>Run {run?.name || runId}</h1>{error && <div role="alert">{error}{!missing && run && !terminal(run.status) && ' Still trying to refresh.'}<button onClick={() => { setError(''); setMissing(false); setAttempt(n => n + 1); }}>Retry run status</button></div>}
    {!run ? (!error && <p role="status">Loading run…</p>) : <>
      <p role="status">{statusLabel(run, cancelRequested)} · {run.completed_units}/{run.total_units} units complete · {run.failed_units} failed · {run.cancelled_units} cancelled</p>
      {!terminal(run.status) && <button disabled={cancelRequested} onClick={() => void cancel()}>{cancelRequested ? 'Cancelling…' : 'Cancel run'}</button>}
      <button onClick={() => onRerun(run)}>Rerun with different engines/presets</button>
      <Button variant="outline" onClick={event => { configTrigger.current = event.currentTarget; setConfiguration(run); }}>Config</Button>
      {run.description && <p>{run.description}</p>}<Usage run={run} />
      <div className="unit-section-heading"><h2>Unit progress</h2><span>{run.completed_units}/{run.total_units} complete · {run.repeats} {run.repeats === 1 ? 'attempt' : 'attempts'} per cell</span></div>
      <div className="unit-table-scroll" role="region" aria-label="Unit progress"><table className="units-table"><caption>Each unit is one session × engine × model/tier/effort × attempt. Repeated model attempts run the same settings independently. Human reference is included once per session.</caption>
        <thead><tr>{['Session', 'Engine', 'Model', 'Tier', 'Effort', 'Attempt', 'Status', 'Stage', 'Output / error'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{run.units.map(unit => { const combo = unit.combo ?? comboFields(run, unit.combo_key ?? unit.preset); return <tr key={unit.unit_id}>
          <td data-label="Session">{unit.session_id}</td><td data-label="Engine">{unit.engine}</td><td data-label="Model">{combo.model || '—'}</td><td data-label="Tier">{combo.tier || '—'}</td><td data-label="Effort">{combo.effort || '—'}</td>
          <td data-label="Attempt">{unit.engine === 'human' ? 'Once' : unit.repeat == null ? '—' : `${unit.repeat + 1} / ${run.repeats}`}</td><td data-label="Status">{unit.status}</td><td data-label="Stage">{unit.stage || '—'}</td>
          <td data-label="Output / error">{unit.error && <p role="alert">{typeof unit.error === 'string' ? unit.error : `${unit.error.code}${unit.error.message ? `: ${unit.error.message}` : ''}`}</p>}{unit.status === 'done' ? <UnitOutput api={api} runId={runId} unit={unit} /> : !unit.error && '—'}</td>
        </tr>; })}</tbody></table></div>
      <CompareView compare={run.compare} />
    </>}<RunConfigDialog returnFocus={configTrigger} run={configuration} onClose={() => setConfiguration(null)} />
  </section>;
}
export function History({ api, onOpen, onRerun }: { api: EvalApi; onOpen: (id: string) => void; onRerun: (run: RunSummary) => void }) {
  const [runs, setRuns] = useState<RunSummary[]>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [cursor, setCursor] = useState<string>();
  const [nextCursor, setNextCursor] = useState<string | null>();
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState(api);
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<Partial<Record<HistoryColumn, string>>>({});
  const [from, setFrom] = useState(''), [to, setTo] = useState('');
  const [sort, setSort] = useState<{ column: HistoryColumn; dir: 'ascending' | 'descending' } | null>(null);
  const [configuration, setConfiguration] = useState<RunSummary | null>(null);
  const configTrigger = useRef<HTMLElement | null>(null);
  const [toDelete, setToDelete] = useState<RunSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const filterId = useId();
  const exhaustive = Boolean(query.trim() || from || to || sort || Object.values(filters).some(Boolean));
  if (source !== api) {
    setSource(api); setRuns(undefined); setCursor(undefined); setNextCursor(undefined); setLoading(true); setError('');
  }
  useEffect(() => {
    const controller = new AbortController();
    api.runs(controller.signal, cursor).then(value => {
      if (controller.signal.aborted) return;
      if (value.next_cursor && value.next_cursor === cursor) throw new Error('History returned the same page cursor. Please retry.');
      setRuns(previous => cursor ? [...(previous ?? []), ...value.runs.filter(run => !previous?.some(old => old.run_id === run.run_id))] : value.runs);
      setNextCursor(value.next_cursor ?? null); setLoading(false);
    }).catch(e => { if (!controller.signal.aborted) { setError(errorMessage(e)); setLoading(false); } });
    return () => controller.abort();
  }, [api, attempt, cursor]);
  // Search, filters and sorting must include the entire history, using summaries only.
  useEffect(() => {
    if (exhaustive && nextCursor && !loading && !error) {
      const timer = setTimeout(() => { setLoading(true); setCursor(nextCursor); }, 0);
      return () => clearTimeout(timer);
    }
  }, [exhaustive, nextCursor, loading, error]);
  const visible = (runs ?? []).filter(run => {
    const date = localDate(run.created_at);
    if ((from && date < from) || (to && date > to)) return false;
    if (historyColumns.some(column => filters[column] && !columnValue(run, column).toLocaleLowerCase().includes(filters[column]!.toLocaleLowerCase()))) return false;
    const haystack = `${JSON.stringify(savedConfiguration(run))} ${historyColumns.map(column => columnValue(run, column)).join(' ')}`;
    return haystack.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  });
  if (sort) visible.sort((a, b) => {
    const comparison = sort.column === 'Date' ? a.created_at.localeCompare(b.created_at) : columnValue(a, sort.column).localeCompare(columnValue(b, sort.column), undefined, { numeric: true, sensitivity: 'base' });
    return sort.dir === 'ascending' ? comparison : -comparison;
  });
  const confirmDelete = async () => {
    if (!toDelete || deleting) return;
    setDeleting(true); setDeleteError('');
    try {
      await api.deleteRun(toDelete.run_id);
      const id = toDelete.run_id;
      setRuns(previous => previous?.map(run => run.run_id === id ? { ...run, status: 'deleting' } : run));
      setToDelete(null);
    } catch (e) { setDeleteError(errorMessage(e)); }
    setDeleting(false);
  };
  const toggle = (column: HistoryColumn) => setSort(previous => ({ column, dir: previous?.column === column && previous.dir === 'ascending' ? 'descending' : 'ascending' }));
  return <section className="history"><h1>History</h1>
    <label htmlFor={`${filterId}-search`} className="history-search">Search history<Input id={`${filterId}-search`} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search saved settings, names, descriptions…" /></label>
    <fieldset className="history-filters"><legend>Filter history</legend>
      <label htmlFor={`${filterId}-from`}>Date from<Input id={`${filterId}-from`} type="date" value={from} onChange={event => setFrom(event.target.value)} /></label><label htmlFor={`${filterId}-to`}>Date to<Input id={`${filterId}-to`} type="date" value={to} onChange={event => setTo(event.target.value)} /></label>
      {historyColumns.filter(column => column !== 'Date').map(column => <label key={column} htmlFor={`${filterId}-${column}`}>{column}<Input id={`${filterId}-${column}`} aria-label={`Filter ${column}`} value={filters[column] ?? ''} onChange={event => setFilters(previous => ({ ...previous, [column]: event.target.value }))} /></label>)}
    </fieldset>
    {error && <div role="alert">{error}{exhaustive && ' Results are incomplete until history finishes loading.'}<Button disabled={loading} onClick={() => { setError(''); setLoading(true); setAttempt(n => n + 1); }}>Retry history</Button></div>}
    {runs && runs.length === 0 ? <p>No saved runs yet.</p> : runs && <>
      <table className="history-table"><thead><tr>{historyColumns.map(column => <th scope="col" key={column} aria-sort={sort?.column === column ? sort.dir : 'none'}><button type="button" className="sort" onClick={() => toggle(column)}>{column}</button></th>)}<th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{visible.map(run => <tr key={run.run_id}>{historyColumns.map(column => <td key={column} data-label={column}>{column === 'Dataset' ? <a href={`?run=${encodeURIComponent(run.run_id)}`} onClick={event => {
          if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onOpen(run.run_id); }
        }}>{inputName(run)}</a> : column === 'Date' ? <time dateTime={run.created_at}>{dateText(run.created_at)}</time> : column === 'Status' ? <Badge variant="outline" className="max-w-full whitespace-normal">{columnValue(run, column)}</Badge> : columnValue(run, column)}</td>)}
          <td className="history-actions" data-label="Actions"><RunActions run={run} onRerun={onRerun} onConfig={(saved, trigger) => { configTrigger.current = trigger; setConfiguration(saved); }} onDelete={target => { setDeleteError(''); setToDelete(target); }} /></td></tr>)}</tbody>
      </table>{visible.length === 0 && <p>No runs match these filters.</p>}</>}
    {loading && <p role="status">{exhaustive ? 'Loading full history for search, filters and sorting…' : 'Loading history…'}</p>}
    {nextCursor && !error && <Button disabled={loading} onClick={() => { setLoading(true); setCursor(nextCursor); }}>Load more</Button>}
    {exhaustive && !loading && !nextCursor && !error && <p role="status">All {runs?.length ?? 0} saved runs searched.</p>}
    <RunConfigDialog returnFocus={configTrigger} run={configuration} onClose={() => setConfiguration(null)} />
    <Dialog open={toDelete !== null} onOpenChange={open => { if (!open && !deleting) setToDelete(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Delete run {toDelete?.name || (toDelete ? inputName(toDelete) : '')}?</DialogTitle>
          <DialogDescription>{toDelete && `${toDelete.total_units} runs, ${toDelete.done_units} reports, ${toDelete.done_units} output files; datasets, gold and sessions stay. This cannot be undone.`}</DialogDescription></DialogHeader>
        {deleteError && <div role="alert">{deleteError}</div>}
        <DialogFooter><Button variant="ghost" disabled={deleting} onClick={() => setToDelete(null)}>Cancel</Button><Button variant="destructive" disabled={deleting} onClick={() => void confirmDelete()}>Delete</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </section>;
}
