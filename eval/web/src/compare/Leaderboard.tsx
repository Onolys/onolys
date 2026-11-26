import type { CompareOverview } from './compareApi';
import type { ComboLegendEntry } from './compareTypes';
import type { CompareUrlState } from './compareUrl';
import { EvalLink, type CompareNavigate } from './CompareLink';
import { failedCombos } from './failedCombos';
import { Chip } from '../ui/Chip';
import { ComboTag } from '../ui/ComboTag';
import { DataTable, type Column } from '../ui/DataTable';
import './leaderboard.css';

type Row = CompareOverview['leaderboard'][number];
const SKIPPED = 'skipped: provider unavailable';
export const fmtUsd = (v: number | null) => v === null ? 'n/a' : `$${v.toFixed(3)}`;
export const fmtSeconds = (v: number | null) => v === null ? 'n/a' : `${v.toFixed(1)} s`;
const fmtPct = (v: number) => `${Math.round(v * 100)}%`;
const failureCount = (row: Row) => row.failures.reduce((n, f) => n + f.count, 0);

function Best() { return <span className="overview-best">★ best</span>; }
function Dash() { return <span className="lb-na" title="n/a: all runs failed">—</span>; }
function Missing({ reason }: { reason: string }) { return <><span className="lb-na">n/a</span><small>{reason}</small></>; }

/** Leaderboard table: plain sortable headers, server-flagged best (never for failed or skipped combos), failed rows tinted red, inline cost/time bars. */
export function Leaderboard({ data, legend, state, navigate, runId }: { data: CompareOverview; legend: ComboLegendEntry[]; state: CompareUrlState; navigate: CompareNavigate; runId: string }) {
 const human = data.has_human && data.verdict.length > 0;
 const failed = new Map(failedCombos(data).filter(f => f.all).map(f => [f.combo_key, f]));
 const isSkipped = (row: Row) => row.na?.reason === SKIPPED;
 const noBest = (row: Row) => failed.has(row.combo_key) || isSkipped(row);
 const usable = data.leaderboard.filter(r => !failed.has(r.combo_key));
 const maxCost = Math.max(0, ...usable.map(r => r.cost.per_run_usd ?? 0));
 const maxTime = Math.max(0, ...usable.map(r => r.time.mean_seconds ?? 0));
 const drill = (combo: string): CompareUrlState => ({ ...state, run: runId, view: 'compare', tab: 'deep', combos: [combo], combo, metric: undefined, code: undefined, session: undefined, turn: undefined, only: undefined });
 const letterOf = (row: Row) => legend.find(e => e.combo.combo_key === row.combo_key)?.letter ?? row.combo_key;
 // Initial order: usable combos first (lowest count error, else fewest failures), failed combos last. Header clicks re-sort.
 const rows = [...data.leaderboard].sort((a, b) => {
  const fa = failed.has(a.combo_key) ? 1 : 0, fb = failed.has(b.combo_key) ? 1 : 0;
  if (fa !== fb) return fa - fb;
  const av = human ? (a.na ? Infinity : a.off ?? Infinity) : failureCount(a), bv = human ? (b.na ? Infinity : b.off ?? Infinity) : failureCount(b);
  if (av === bv) return 0; // also covers Infinity vs Infinity (n/a vs n/a), which would otherwise be NaN
  return av < bv ? -1 : 1;
 });
 const quality = (key: 'globals_within_1' | 'line_accuracy' | 'macro_f1', header: string, fmt: (v: number) => string): Column<Row> => ({
  key, header,
  value: r => r[key].na ? null : r[key].value,
  render: r => { const c = r[key]; return c.na ? <Missing reason={c.na.reason} /> : <><span>{c.value === null ? 'n/a' : fmt(c.value)}</span>{c.best && !noBest(r) && <Best />}<small>n={c.n}</small></>; },
 });
 const bar = (kind: 'cost' | 'time', value: number | null, max: number) => value !== null && max > 0 ? <span className="lb-bar" data-bar={kind} aria-hidden="true"><i style={{ width: `${Math.max(2, Math.round(value / max * 100))}%` }} /></span> : <span className="lb-bar" data-bar={kind} aria-hidden="true" />;
 const columns: Column<Row>[] = [
  { key: 'combo', header: 'Combo', value: r => letterOf(r), render: r => {
   const index = Math.max(0, legend.findIndex(e => e.combo.combo_key === r.combo_key)), fail = failed.get(r.combo_key);
   return <><EvalLink state={drill(r.combo_key)} navigate={navigate}><ComboTag index={index} letter={letterOf(r)} /></EvalLink>
    <small className="lb-label" title={legend[index]?.label ?? r.combo_key}>{legend[index]?.label ?? r.combo_key}</small>
    {fail && <span className="lb-nowrap" title={`failed: ${fail.code}`}><Chip tone="danger">failed</Chip></span>}{isSkipped(r) && <Chip tone="muted">skipped</Chip>}</>;
  } },
  ...(human ? [
   { key: 'count', header: 'Count error', value: (r: Row) => r.na ? null : r.off, render: (r: Row) => r.na ? <Missing reason={r.na.reason} /> : <><span>{r.off === null ? 'n/a' : r.off.toFixed(2)}</span>{r.best && !noBest(r) && <Best />}<small>{r.n} of {r.of} paired</small></> } as Column<Row>,
   quality('globals_within_1', 'Globals within ±1', fmtPct), quality('line_accuracy', 'Line match accuracy', fmtPct), quality('macro_f1', 'Line match macro F1', v => v.toFixed(2)),
  ] : []),
  { key: 'fails', header: 'Fails', value: failureCount, render: r => { const fail = failed.get(r.combo_key); return <>{fail ? <span className="lb-nowrap" title={fail.code}><Chip tone="danger">all failed</Chip></span> : r.failures.length ? r.failures.map(f => <span key={f.code} className="lb-code" title={`${f.count} × ${f.code}`}>{f.count} × {f.code}</span>) : <span>0</span>}{r.operational_best.failures && !noBest(r) && <Best />}</>; } },
  { key: 'cost', header: 'Cost', value: r => r.cost.na ? null : r.cost.per_run_usd, render: r => failed.has(r.combo_key) ? <Dash /> : r.cost.na ? <Missing reason={r.cost.na.reason} /> : <><span>{fmtUsd(r.cost.per_run_usd)}</span>{r.operational_best.cost && !noBest(r) && <Best />}{bar('cost', r.cost.per_run_usd, maxCost)}<small>n={r.cost.n} runs · per run</small></> },
  { key: 'time', header: 'Time', value: r => r.time.mean_seconds, render: r => failed.has(r.combo_key) ? <Dash /> : <><span>{fmtSeconds(r.time.mean_seconds)}</span>{r.operational_best.time && !noBest(r) && <Best />}{bar('time', r.time.mean_seconds, maxTime)}<small>n={r.time.n} runs</small></> },
 ];
 return <div className="overview-leaderboard"><DataTable rows={rows} columns={columns} rowKey={r => r.combo_key} rowTone={r => failed.has(r.combo_key) ? 'danger' : undefined} searchLabel="Search combos" /></div>;
}
