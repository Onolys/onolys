import { useEffect, useState } from 'react';
import { Button } from '@onolys/ui';
import { Loader2 } from 'lucide-react';
import type { EvalApi, RunDetail, RunUnit } from '../api';
import { JsonDialog } from '../JsonViewer';
import { Chip, type ChipTone } from '../ui/Chip';
import { CopyField } from '../ui/CopyField';
import { DataTable, type Column } from '../ui/DataTable';
import { Note } from '../ui/Note';
import { describeError } from './errorCatalog';
import { comboFields } from './comboFields';
import { UnitErrorBadge } from './UnitErrorDialog';
import './run.css';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Could not load run. Please try again.';
const STATUS_TONE: Record<string, ChipTone> = { done: 'success', failed: 'danger', running: 'info', queued: 'neutral', waiting: 'neutral', skipped: 'warning', cancelled: 'muted' };
export const unitErrorCode = (unit: RunUnit) => typeof unit.error === 'string' ? unit.error : unit.error?.code;
const unitErrorNote = (unit: RunUnit) => typeof unit.error === 'string' ? unit.error : unit.error?.message ?? describeError(unit.error?.code).title;

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
    <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>View JSON</Button>
    <JsonDialog open={open} onOpenChange={setOpen} title="Unit output" extra={<CopyField label="Unit id" value={unit.unit_id} />}
      value={output} loading={open && !error && output === undefined} error={error || undefined}
      onRetry={() => { setError(''); setAttempt(n => n + 1); }} />
  </>;
}

type Filters = { status: string; engine: string; model: string };
function UnitFilters({ units, modelOf, setFilter }: { units: readonly RunUnit[]; modelOf: (unit: RunUnit) => string; setFilter: (fn: ((unit: RunUnit) => boolean) | null) => void }) {
  const [values, setValues] = useState<Filters>({ status: '', engine: '', model: '' });
  const options = (get: (unit: RunUnit) => string) => [...new Set(units.map(get).filter(Boolean))].sort();
  const change = (key: keyof Filters) => (value: string) => {
    const next = { ...values, [key]: value }; setValues(next);
    setFilter(next.status || next.engine || next.model ? unit => (!next.status || unit.status === next.status) && (!next.engine || unit.engine === next.engine) && (!next.model || modelOf(unit) === next.model) : null);
  };
  const select = (key: keyof Filters, label: string, all: string, items: string[]) =>
    <select className="run-filter" aria-label={label} value={values[key]} onChange={e => change(key)(e.target.value)}>
      <option value="">{all}</option>{items.map(item => <option key={item} value={item}>{item}</option>)}
    </select>;
  return <>
    {select('status', 'Filter by status', 'All statuses', options(unit => unit.status))}
    {select('engine', 'Filter by engine', 'All engines', options(unit => unit.engine))}
    {select('model', 'Filter by model', 'All models', options(modelOf))}
  </>;
}

/** Unit progress: searchable, filterable, sortable fixed-layout table. Failed units show an error badge; done units open their output in a popup. */
export function UnitTable({ api, runId, run }: { api: EvalApi; runId: string; run: RunDetail }) {
  const comboOf = (unit: RunUnit) => unit.combo ?? comboFields(run, unit.combo_key ?? unit.preset);
  const modelOf = (unit: RunUnit) => comboOf(unit).model || '';
  const attempt = (unit: RunUnit) => unit.engine === 'human' ? 'Once' : unit.repeat == null ? null : `${unit.repeat + 1} / ${run.repeats}`;
  const result = (unit: RunUnit) => unit.status === 'skipped' ? `n/a${unit.error ? ` — ${unitErrorNote(unit)}` : ''}` : unit.error ? unitErrorCode(unit) || 'unknown' : unit.status === 'done' ? 'Output' : null;
  const columns: Column<RunUnit>[] = [
    { key: 'session', header: 'Session', value: u => u.session_id },
    { key: 'engine', header: 'Engine', value: u => u.engine },
    { key: 'model', header: 'Model', value: u => modelOf(u) || null, render: u => modelOf(u) || '—' },
    { key: 'tier', header: 'Tier', priority: 'low', value: u => comboOf(u).tier || null, render: u => comboOf(u).tier || '—' },
    { key: 'effort', header: 'Effort', priority: 'low', value: u => comboOf(u).effort || null, render: u => comboOf(u).effort || '—' },
    { key: 'attempt', header: 'Attempt', value: attempt, render: u => attempt(u) ?? '—' },
    { key: 'status', header: 'Status', value: u => u.status, render: u => <Chip tone={STATUS_TONE[u.status] ?? 'neutral'} icon={u.status === 'running' ? <Loader2 aria-hidden="true" className="run-spin" /> : undefined}>{u.status}</Chip> },
    { key: 'stage', header: 'Stage', priority: 'low', value: u => u.stage || null, render: u => u.stage || '—' },
    { key: 'result', header: 'Output / error', value: result, render: u => u.status === 'skipped' ? result(u)
      : u.error ? <UnitErrorBadge run={run} unit={u} code={unitErrorCode(u)} />
      : u.status === 'done' ? <UnitOutput api={api} runId={runId} unit={u} /> : '—' },
  ];
  return <section className="run-units" aria-label="Unit progress">
    <div className="unit-section-heading"><h2>Unit progress</h2><span>{run.done_units}/{run.total_units} runs done · {run.repeats} {run.repeats === 1 ? 'attempt' : 'attempts'} per cell</span></div>
    <p className="run-units-explainer">Each row is one run of one session with one engine and model setup.</p>
    <DataTable rows={run.units} columns={columns} rowKey={u => u.unit_id} searchLabel="Search units" empty="No units match."
      rowTone={u => u.status === 'failed' ? 'danger' : undefined}
      filters={({ setFilter }) => <UnitFilters units={run.units} modelOf={modelOf} setFilter={setFilter} />} />
    <Note>Repeated model attempts run the same settings independently. Human reference is included once per session.</Note>
  </section>;
}
