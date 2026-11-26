import { ComboTag } from '../../ui/ComboTag';
import { comboColor } from '../../ui/chart';
import { DataTable, type Column } from '../../ui/DataTable';
import { Disclosure } from '../../ui/Disclosure';
import { Note } from '../../ui/Note';
import type { LineMetrics } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import '../deepDive.css';

type Stats = LineMetrics['combos'][string]['per_code'][string];
interface Row { code: string; by: Record<string, Stats | undefined> }
const num = (value: number | null | undefined) => (value === null || value === undefined ? 'n/a' : value.toFixed(2));

/** Per-code precision / recall / F1 for the combos with line-level output; F1 gets an inline bar, P and R sit beneath. */
export function PrfTable({ lines, series }: { lines: LineMetrics; series: DotSeries[] }) {
 const codes = [...new Set(series.flatMap(s => Object.keys(lines.combos[s.key]?.per_code ?? {})))];
 const rows: Row[] = codes.map(code => ({ code, by: Object.fromEntries(series.map(s => [s.key, lines.combos[s.key]?.per_code[code]])) }));
 const columns: Column<Row>[] = [
  { key: 'code', header: 'Code', value: row => row.code, width: '24%', render: row => <span data-prf-row={row.code}>{row.code}</span> },
  ...series.map((s): Column<Row> => ({
   key: s.key, header: `${s.letter} · F1`, value: row => row.by[s.key]?.f1 ?? null,
   render: row => {
    const stats = row.by[s.key];
    if (!stats || stats.f1 === null) return <span className="deep-f1-na">n/a</span>;
    return <span className="deep-f1">
     <span className="deep-f1-line"><span className="deep-f1-track" aria-hidden="true"><span data-f1-bar={s.key} style={{ width: `${Math.max(0, Math.min(1, stats.f1)) * 100}%`, background: comboColor(s.index) }}/></span><strong>{num(stats.f1)}</strong></span>
     <small className="deep-f1-sub">P {num(stats.p)} · R {num(stats.r)}</small>
    </span>;
   },
  })),
 ];
 const twin: Column<Row>[] = [
  { key: 'code', header: 'Code', value: row => row.code },
  ...series.flatMap((s): Column<Row>[] => (['p', 'r', 'f1'] as const).map(k => ({ key: `${s.key}-${k}`, header: `${s.letter} · ${k === 'f1' ? 'F1' : k.toUpperCase()}`, value: (row: Row) => num(row.by[s.key]?.[k]) }))),
 ];
 return <section className="deep-card deep-prf">
  <div className="deep-card-head"><div><h3>Precision / recall / F1</h3>
   <Note>{lines.codes_labeled.length} of 10 codes labeled</Note></div>
   <span className="deep-prf-legend">{series.map(s => <ComboTag key={s.key} index={s.index} letter={s.letter}/>)}</span></div>
  <DataTable rows={rows} columns={columns} rowKey={row => row.code} ariaLabel="Line agreement" searchLabel="Search codes"/>
  <Disclosure label="Show data"><DataTable rows={rows} columns={twin} rowKey={row => row.code} ariaLabel="P/R/F1 data" searchLabel="Search codes"/></Disclosure>
  {lines.dataset_notes.map((note, i) => <Note key={i}>{note}</Note>)}
  <Note>Precision: when the combo says X, how often the human agreed. Recall: of the human's X lines, how many it found. F1 is low if either is low.</Note>
  <Note>{series.map(s => { const c = lines.combos[s.key]; return `${s.letter}: n=${c.n} sessions · ${c.aligned} aligned lines · ${c.repeats} repeats`; }).join('  |  ')}</Note>
 </section>;
}
