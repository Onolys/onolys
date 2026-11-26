import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import type { CompareAnalysis, ValueCell } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import './reliability.css';

type Reliability = CompareAnalysis['reliability'][string];
interface Row { key: string; rel: Reliability | undefined }
const LEVELS: Record<string, string> = { technical: 'Technical', relational: 'Relational', pct_cr: '%CR', reflection_question_ratio: 'R:Q' };
const pct = (v: number) => `${Math.round(v * 100)}%`;
const na = (reason?: string) => `n/a${reason ? ` - ${reason}` : ''}`;
const cellText = (c: ValueCell) => c.na || c.value === null ? `${na(c.na?.reason)} · n=${c.n}` : `${pct(c.value)} · n=${c.n}`;
const failTotal = (r: Reliability | undefined) => r ? r.failures.reduce((n, f) => n + f.count, 0) : null;

/** Reliability: repeat agreement, fails and time per combo. Sortable plain headers; all-failed rows shaded red and never "best". `best` carries the server's operational-best flags (not computed here). */
export function ReliabilityTable({ data, legend, failed, best = {} }: { data: CompareAnalysis; legend: ComboLegendEntry[]; failed: FailedCombo[]; best?: Record<string, { failures: boolean; time: boolean }> }) {
 const failedAll = new Map(failed.filter(f => f.all).map(f => [f.combo_key, f]));
 const index = (key: string) => Math.max(0, legend.findIndex(e => e.combo.combo_key === key));
 const letter = (key: string) => legend.find(e => e.combo.combo_key === key)?.letter ?? key;
 const rows: Row[] = data.combos.map(c => ({ key: c.combo_key, rel: data.reliability[c.combo_key] }));
 const isBest = (key: string, kind: 'failures' | 'time') => !failedAll.has(key) && best[key]?.[kind] === true;
 const Star = ({ show }: { show: boolean }) => show ? <span className="rel-best">★ best</span> : null;
 const dash = (r: Row) => failedAll.has(r.key) || !r.rel;
 const columns: Column<Row>[] = [
  { key: 'combo', header: 'Combo', width: '18%', value: r => letter(r.key), render: r => <><ComboTag index={index(r.key)} letter={letter(r.key)} />
   {data.skipped_combos.includes(r.key) && <Chip tone="muted">skipped</Chip>}
   {failedAll.has(r.key) && <span title={`failed: ${failedAll.get(r.key)!.code}`}><Chip tone="danger">all runs failed</Chip></span>}</> },
  { key: 'levels', header: 'Same MITI level', width: '25%', priority: 'low', sortable: false, value: r => r.rel?.na ? null : r.rel ? Object.values(r.rel.levels).map(c => c.value).join(' ') : null,
   render: r => dash(r) ? <span className="rel-na">{r.rel ? '—' : 'n/a'}</span> : r.rel!.na ? <span className="rel-na">{na(r.rel!.na!.reason)}</span> : <>{Object.entries(r.rel!.levels).map(([m, c]) => <span key={m} className="rel-line">{LEVELS[m] ?? m} {cellText(c)}</span>)}</> },
  { key: 'agreement', header: 'Repeat agreement', width: '27%', value: r => dash(r) ? null : r.rel!.repeat_agreement.lines.value,
   render: r => dash(r) ? <span className="rel-na">{r.rel ? '—' : 'n/a'}</span> : <>{(['globals', 'lines'] as const).map(m => { const c = r.rel!.repeat_agreement[m]; return <span key={m} className="rel-line">{c.na || c.value === null ? `${m}: ${na(c.na?.reason)} · n=${c.n}` : <><b>{m} {pct(c.value)}</b> · {c.agree} of {c.n} agree</>}</span>; })}</> },
  { key: 'fails', header: 'Fails', width: '14%', value: r => failedAll.has(r.key) ? Number.MAX_SAFE_INTEGER : failTotal(r.rel),
   render: r => failedAll.has(r.key) ? <span className="rel-na">—</span> : !r.rel ? <span className="rel-na">n/a</span> : <>{r.rel.failures.length ? r.rel.failures.map(f => <span key={f.code} className="rel-line" title={`${f.count} × ${f.code}`}>{f.count} × {f.code}</span>) : <span>0</span>}<Star show={isBest(r.key, 'failures')} /></> },
  { key: 'time', header: 'Time', width: '16%', value: r => failedAll.has(r.key) ? null : r.rel?.time.mean_seconds ?? null,
   render: r => dash(r) ? <span className="rel-na">{r.rel ? '—' : 'n/a'}</span> : <><span>{r.rel!.time.mean_seconds === null ? 'n/a' : `${Number(r.rel!.time.mean_seconds.toFixed(1))} s`}</span><Star show={isBest(r.key, 'time')} /><small>n={r.rel!.time.n} · retried {r.rel!.time.retried_runs}</small></> },
 ];
 return <section className="rel-card" aria-label="Reliability">
  <h3 className="rel-title">Reliability</h3>
  <p className="rel-caption">Do repeats of a combo agree, and does it finish its runs? Each n counts observations.</p>
  <div className="rel-table"><DataTable ariaLabel="Reliability" rows={rows} columns={columns} rowKey={r => r.key} rowTone={r => failedAll.has(r.key) ? 'danger' : undefined} searchLabel="Search combos" /></div>
 </section>;
}
