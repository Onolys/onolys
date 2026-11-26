import { useEffect, useId, useRef, useState } from 'react';
import { Badge, Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Input } from '@onolys/ui';
import { ApiError } from './api';
import { CancelRunDialog, CancellationNote, canCancelRun, isActiveRun, mergeRunStatus } from './CancelRunDialog';
import { PartialBadge, ProviderSkipNotices, RunErrorNote, partialStatusText, providerName } from './RunStatus';
import { RunConfigDialog, savedConfiguration } from './RunConfigDialog';
import { ColdStartNotice } from './ColdStart';
import { JsonDialog } from './JsonViewer';
import './runs.css';
import { CompareLink, type CompareNavigate } from './compare/CompareLink';
import { navigateEval } from './evalNavigation';
import type { EvalApi, RunDetail, RunSummary, RunUnit } from './api';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not load run. Please try again.';
const terminal = (status: string) => !['queued', 'running'].includes(status);
const deletable = (status: string) => ['done', 'partial', 'failed', 'cancelled'].includes(status);
const statusLabel = (run: RunSummary, cancelRequested = false) => cancelRequested && !terminal(run.status) ? 'cancelling' : partialStatusText(run) ?? (run.status === 'cancelled' ? 'Cancelled — no runs completed' : run.status);
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
function RunActions({ run, onRerun, onConfig, onDelete, onCancel }: { onCancel: (run: RunSummary, trigger: HTMLElement | null) => void; run: RunSummary; onRerun: (run: RunSummary) => void; onDelete: (run: RunSummary) => void; onConfig: (run: RunSummary, trigger: HTMLElement | null) => void }) {
  const trigger = useRef<HTMLButtonElement>(null);
  const openingConfig = useRef(false);
  return <DropdownMenu><DropdownMenuTrigger asChild><Button ref={trigger} variant="ghost" size="icon" aria-label={`Actions for ${run.name || inputName(run)}`}>⋮</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" onCloseAutoFocus={event => {
      if (openingConfig.current) { event.preventDefault(); openingConfig.current = false; }
    }}><DropdownMenuItem onSelect={() => onRerun(run)}>Rerun</DropdownMenuItem><DropdownMenuItem onSelect={() => { openingConfig.current = true; onConfig(run, trigger.current); }}>Config</DropdownMenuItem>{canCancelRun(run) && <DropdownMenuItem onSelect={() => { openingConfig.current = true; onCancel(run, trigger.current); }}>Cancel run</DropdownMenuItem>}<DropdownMenuItem disabled={!deletable(run.status)} onSelect={() => onDelete(run)}>Delete</DropdownMenuItem></DropdownMenuContent>
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
  return <>
    <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>View JSON {unit.unit_id}</Button>
    <JsonDialog open={open} onOpenChange={setOpen} title={`Unit ${unit.unit_id} output`} value={output} loading={open && !error && output === undefined} error={error || undefined}
      onRetry={() => { setError(''); setAttempt(n => n + 1); }} />
  </>;
}
export function RunView({ api, runId, onRerun, onNavigate = navigateEval }: { api: EvalApi; runId: string; onRerun: (run: RunSummary) => void; onNavigate?: CompareNavigate }) {
  const [run, setRun] = useState<RunDetail>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [toCancel, setToCancel] = useState<RunSummary | null>(null);
  const cancelTrigger = useRef<HTMLElement | null>(null);
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
        setRun(previous => previous ? mergeRunStatus(previous, value) : value);
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
  const cancelRequested = run?.cancel_requested === true;
  return <section className="run-detail"><div className="unit-section-heading"><h1>Run {run?.name || runId}</h1>{run && <PartialBadge run={run} />}</div>{error && <div role="alert">{error}{!missing && run && !terminal(run.status) && ' Still trying to refresh.'}<button onClick={() => { setError(''); setMissing(false); setAttempt(n => n + 1); }}>Retry run status</button></div>}
    {!run ? (!error && <p role="status">Loading run…</p>) : <>
      <p role="status">{run.status === 'partial' ? 'partial' : statusLabel(run, cancelRequested)} · {run.done_units}/{run.total_units} runs done{isActiveRun(run) && ` · ${run.running_units ?? 0} running · ${run.queued_units ?? 0} queued`} · {run.failed_units} failed · {run.cancelled_units} cancelled</p>
      <RunErrorNote run={run} />
      <CancellationNote run={run} />
      <CompareLink run={run} navigate={onNavigate} />
      {canCancelRun(run) && <Button onClick={event => { cancelTrigger.current = event.currentTarget; setToCancel(run); }}>Cancel run</Button>}
      <button onClick={() => onRerun(run)}>Rerun with different engines/presets</button>
      <Button variant="outline" onClick={event => { configTrigger.current = event.currentTarget; setConfiguration(run); }}>Config</Button>
      {run.description && <p>{run.description}</p>}<Usage run={run} />
      <ProviderSkipNotices skips={run.provider_skips} />
      {run.provider_cooldowns?.map(cooldown => <p key={cooldown.provider}>{providerName(cooldown.provider)} is busy — waiting to retry</p>)}
      <div className="unit-section-heading"><h2>Unit progress</h2><span>{run.done_units}/{run.total_units} runs done · {run.repeats} {run.repeats === 1 ? 'attempt' : 'attempts'} per cell</span></div>
      <div className="unit-table-scroll" role="region" aria-label="Unit progress"><table className="units-table"><caption>Each unit is one session × engine × model/tier/effort × attempt. Repeated model attempts run the same settings independently. Human reference is included once per session.</caption>
        <thead><tr>{['Session', 'Engine', 'Model', 'Tier', 'Effort', 'Attempt', 'Status', 'Stage', 'Output / error'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{run.units.map(unit => { const combo = unit.combo ?? comboFields(run, unit.combo_key ?? unit.preset); return <tr key={unit.unit_id}>
          <td data-label="Session">{unit.session_id}</td><td data-label="Engine">{unit.engine}</td><td data-label="Model">{combo.model || '—'}</td><td data-label="Tier">{combo.tier || '—'}</td><td data-label="Effort">{combo.effort || '—'}</td>
          <td data-label="Attempt">{unit.engine === 'human' ? 'Once' : unit.repeat == null ? '—' : `${unit.repeat + 1} / ${run.repeats}`}</td><td data-label="Status">{unit.status}</td><td data-label="Stage">{unit.stage || '—'}</td>
          <td data-label="Output / error">{unit.status === 'skipped' ? <>n/a{unit.error && ` — ${typeof unit.error === 'string' ? unit.error : unit.error.message ?? unit.error.code}`}</> : <>{unit.error && <p role="alert">{typeof unit.error === 'string' ? unit.error : `${unit.error.code}${unit.error.message ? `: ${unit.error.message}` : ''}`}</p>}{unit.status === 'done' ? <UnitOutput api={api} runId={runId} unit={unit} /> : !unit.error && '—'}</>}</td>
        </tr>; })}</tbody></table></div>
    </>}<CancelRunDialog api={api} run={toCancel} returnFocus={cancelTrigger} onClose={() => setToCancel(null)} onUpdated={fresh => { if (!isActiveRun(fresh)) stop.current(); setRun(fresh); }} /><RunConfigDialog returnFocus={configTrigger} run={configuration} onClose={() => setConfiguration(null)} />
  </section>;
}
export function History({ api, onOpen, onRerun, onNavigate = navigateEval }: { api: EvalApi; onOpen: (id: string) => void; onRerun: (run: RunSummary) => void; onNavigate?: CompareNavigate }) {
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
  const [toCancel, setToCancel] = useState<RunSummary | null>(null);
  const cancelTrigger = useRef<HTMLElement | null>(null);
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
  const activeIds = JSON.stringify((runs ?? []).filter(isActiveRun).map(run => run.run_id));
  useEffect(() => {
    const ids = JSON.parse(activeIds) as string[];
    if (!ids.length) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await Promise.all(ids.map(async id => {
        try {
          const fresh = await api.run(id, controller.signal);
          if (!controller.signal.aborted) setRuns(previous => previous?.map(old => old.run_id === id ? mergeRunStatus(old, fresh) : old));
        } catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)); }
      }));
      if (!controller.signal.aborted) timer = setTimeout(() => void poll(), POLL_MS);
    };
    timer = setTimeout(() => void poll(), POLL_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, activeIds, attempt]);
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
        }}>{inputName(run)}</a> : column === 'Date' ? <time dateTime={run.created_at}>{dateText(run.created_at)}</time> : column === 'Status' ? <div>{run.status === 'partial' ? <PartialBadge run={run} /> : <Badge variant="outline" className="max-w-full whitespace-normal">{columnValue(run, column)}</Badge>}{isActiveRun(run) && <p className="text-sm text-muted-foreground">{run.done_units} of {run.total_units} runs done{run.running_units ? `, ${run.running_units} running` : ''}</p>}<CancellationNote run={run} /><ProviderSkipNotices skips={run.provider_skips} short /></div> : columnValue(run, column)}</td>)}
          <td className="history-actions" data-label="Actions"><CompareLink run={run} navigate={onNavigate} /><RunActions run={run} onCancel={(saved, trigger) => { cancelTrigger.current = trigger; setToCancel(saved); }} onRerun={onRerun} onConfig={(saved, trigger) => { configTrigger.current = trigger; setConfiguration(saved); }} onDelete={target => { setDeleteError(''); setToDelete(target); }} /></td></tr>)}</tbody>
      </table>{visible.length === 0 && <p>No runs match these filters.</p>}</>}
    {loading && <p role="status">{exhaustive ? 'Loading full history for search, filters and sorting…' : 'Loading history…'}</p>}<ColdStartNotice pending={loading && !error && !runs?.length} />
    {nextCursor && !error && <Button disabled={loading} onClick={() => { setLoading(true); setCursor(nextCursor); }}>Load more</Button>}
    {exhaustive && !loading && !nextCursor && !error && <p role="status">All {runs?.length ?? 0} saved runs searched.</p>}
    <CancelRunDialog api={api} run={toCancel} returnFocus={cancelTrigger} onClose={() => setToCancel(null)} onUpdated={fresh => setRuns(previous => previous?.map(old => old.run_id === fresh.run_id ? fresh : old))} />
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
