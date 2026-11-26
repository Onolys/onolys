import { Chip } from '../../ui/Chip';
import { ChartFrame } from '../../ui/ChartFrame';
import { ComboTag } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import { Disclosure } from '../../ui/Disclosure';
import type { CompareCell } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import '../deepDive.css';

const BUCKETS = [{ id: 'same', label: 'same' }, { id: 'off1', label: 'off by 1' }, { id: 'off2plus', label: 'off by 2+' }] as const;
export type BucketId = (typeof BUCKETS)[number]['id'];
export interface MissGlobal { metric: string; title: string; cells: Record<string, CompareCell> }

const naText = (cell: CompareCell | undefined) => (cell?.na ? `n/a - ${cell.na.reason}` : 'n/a');
const pct = (value: number | undefined) => (value === undefined ? 'n/a' : `${Math.round(value * 100)}%`);

type Buckets = NonNullable<CompareCell['buckets']>;
/** Largest-remainder rounding so the three displayed percents always total 100. */
function bucketPcts(b: Buckets | undefined): Record<BucketId, string> | undefined {
 if (!b) return undefined;
 const raw = BUCKETS.map(x => b[x.id] * 100), floors = raw.map(Math.floor);
 let left = Math.round(raw.reduce((x, y) => x + y, 0)) - floors.reduce((x, y) => x + y, 0);
 const order = raw.map((v, i) => [v - floors[i], i] as const).sort((x, y) => y[0] - x[0] || x[1] - y[1]);
 for (const [, i] of order) { if (left <= 0) break; floors[i] += 1; left -= 1; }
 return Object.fromEntries(BUCKETS.map((x, i) => [x.id, `${floors[i]}%`])) as Record<BucketId, string>;
}

function Bars({ global, series }: { global: MissGlobal; series: DotSeries[] }) {
 const legend = <div className="deep-bucket-legend" role="group" aria-label="Miss bucket legend">{BUCKETS.map(b => <span key={b.id} className="deep-legend-item"><span className={`deep-swatch deep-${b.id}`} aria-hidden="true"/>{b.label}</span>)}</div>;
 const columns: Column<MissGlobal['cells'][string] & { combo: DotSeries }>[] = [
  { key: 'combo', header: 'Combo', value: row => row.combo.letter },
  { key: 'miss', header: 'Average miss', value: row => (row.na || row.off === null ? naText(row) : row.off) },
  { key: 'within', header: 'Within ±1', value: row => pct(row.within_1) },
  { key: 'same', header: 'Same', value: row => bucketPcts(row.buckets)?.same ?? 'n/a' },
  { key: 'off1', header: 'Off by 1', value: row => bucketPcts(row.buckets)?.off1 ?? 'n/a' },
  { key: 'off2plus', header: 'Off by 2+', value: row => bucketPcts(row.buckets)?.off2plus ?? 'n/a' },
  { key: 'paired', header: 'Paired sessions', value: row => `paired ${row.n} of ${row.of} · ${row.repeats} repeats` },
 ];
 const rows = series.filter(s => global.cells[s.key]).map(s => ({ ...global.cells[s.key], combo: s }));
 return <ChartFrame title={`How far off are the ratings? ${global.title}`} caption="Share of ratings that match the human exactly, miss by one point, or miss by two or more." legend={legend}
  table={<DataTable rows={rows} columns={columns} rowKey={row => row.combo.key} ariaLabel={`${global.metric} misses`} searchLabel="Search combos"/>}>
  {series.map(s => {
   const cell = global.cells[s.key], pcts = bucketPcts(cell?.buckets);
   return <div key={s.key} className="deep-bucket-row">
    <ComboTag index={s.index} letter={s.letter}/>
    {!cell || cell.na || !cell.buckets ? <Chip tone="muted" icon={<span aria-hidden="true"/>}><span title={cell ? `paired ${cell.n} of ${cell.of} · ${cell.repeats} repeats` : undefined}>{naText(cell)}</span></Chip> : <>
     <div className="deep-stack" role="img" aria-label={`${s.letter}: same ${pcts!.same}, off by 1 ${pcts!.off1}, off by 2+ ${pcts!.off2plus}`}>
      {BUCKETS.map(b => <span key={b.id} data-bucket={b.id} className={`deep-seg deep-${b.id}`} style={{ width: `${cell.buckets![b.id] * 100}%` }} title={`${b.label}: ${pcts![b.id]} of ratings`}>{cell.buckets![b.id] > 0 ? pcts![b.id] : ''}</span>)}
     </div>
     <div className="deep-bucket-stats"><strong>miss {cell.off ?? 'n/a'}</strong><span>within ±1: {pct(cell.within_1)}</span></div></>}
   </div>;
  })}
 </ChartFrame>;
}

/** Secondary view, collapsed by default: 100% stacked miss-bucket bars per global. */
export function MissBuckets({ globals, series }: { globals: MissGlobal[]; series: DotSeries[] }) {
 return <section className="deep-miss" aria-label="Miss buckets">
  <Disclosure label="Show miss-bucket bars"><div className="deep-grid">{globals.map(global => <div key={global.metric} className="deep-bucket-card"><Bars global={global} series={series}/></div>)}</div></Disclosure>
 </section>;
}
