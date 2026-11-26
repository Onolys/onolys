import { Chip, type ChipTone } from '../../ui/Chip';
import { ChartFrame } from '../../ui/ChartFrame';
import { ComboTag } from '../../ui/ComboTag';
import { comboColor, HUMAN_COLOR } from '../../ui/chart';
import { DataTable, type Column } from '../../ui/DataTable';
import { Note } from '../../ui/Note';
import type { CompareCell, CompareDeepDive, MetricCells, NA, ValueCell } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import '../deepDive.css';

const naText = (na: NA | undefined) => `n/a${na ? ` - ${na.reason}` : ''}`;
const paired = (cell: CompareCell) => `paired ${cell.n} of ${cell.of} · ${cell.repeats} repeats`;

/** Bias tone: green up to 10%, amber 10-20%, red above 20% (on the rounded percent shown in the chip). */
export function biasTone(pct: number | null | undefined): ChipTone {
 if (pct === null || pct === undefined) return 'muted';
 const size = Math.round(Math.abs(pct));
 return size <= 10 ? 'success' : size <= 20 ? 'warning' : 'danger';
}
export function biasText(pct: number): string {
 const size = Math.round(Math.abs(pct));
 return size === 0 ? 'no count bias' : `${pct > 0 ? 'over' : 'under'}-counts ${size}%`;
}
const countText = (value: number | null | undefined, na: NA | undefined) => (value === null || value === undefined ? naText(na) : String(value));

interface Row { key: string; label: string; cell?: CompareCell; bias?: ValueCell; series?: DotSeries }

function CountCard({ code, human, cells, bias, series }: { code: string; human: CompareDeepDive['counts']['human']; cells: MetricCells[string]; bias: Record<string, ValueCell> | undefined; series: DotSeries[] }) {
 const h = human?.[code];
 const rows: Row[] = series.map(s => ({ key: s.key, label: s.letter, cell: cells?.[s.key], bias: bias?.[s.key], series: s }));
 const max = Math.max(0, h?.value ?? 0, ...rows.map(r => r.cell?.value ?? 0));
 const width = (value: number | null | undefined) => `${max > 0 && value ? Math.min(100, (value / max) * 100) : 0}%`;
 const columns: Column<Row | 'human'>[] = [
  { key: 'who', header: 'Reference / combo', value: r => (r === 'human' ? 'Human' : r.label) },
  { key: 'mean', header: 'Mean count', value: r => (r === 'human' ? countText(h?.value, h?.na) : r.cell?.na || r.cell?.value === null ? naText(r.cell?.na) : r.cell?.value ?? 'n/a') },
  { key: 'bias', header: 'Bias', value: r => (r === 'human' ? 'Reference' : !r.bias || r.bias.na || r.bias.value === null ? naText(r.bias?.na) : biasText(r.bias.value)) },
  { key: 'paired', header: 'Paired sessions', value: r => (r === 'human' ? `n=${h?.n ?? 0}` : r.cell ? paired(r.cell) : 'n/a') },
 ];
 return <div data-count-card={code}>
  <ChartFrame title={code} caption="Average count per session, Human vs the selected combos, on the same paired sessions."
   table={<DataTable rows={['human' as const, ...rows]} columns={columns} rowKey={r => (r === 'human' ? 'human' : r.key)} ariaLabel={`${code} counts`} searchLabel="Search combos"/>}>
   <div className="deep-count-row" data-human-count={code}>
    <span className="deep-count-label"><span className="deep-human-swatch" aria-hidden="true"/>Human</span>
    <div className="deep-count-track"><span data-count-fill="human" style={{ width: width(h?.value), background: HUMAN_COLOR }}/></div>
    <span className="deep-count-value"><strong>{countText(h?.value, h?.na)}</strong> <small>n={h?.n ?? 0}</small></span>
   </div>
   {rows.map(r => {
    const unavailable = !r.cell || r.cell.na || r.cell.value === null;
    const b = r.bias;
    return <div key={r.key} className="deep-count-row">
     <span className="deep-count-label"><ComboTag index={r.series!.index} letter={r.label}/></span>
     <div className="deep-count-track"><span data-count-fill={r.key} style={{ width: width(r.cell?.value), background: comboColor(r.series!.index) }}/></div>
     <span className="deep-count-value"><strong>{unavailable ? naText(r.cell?.na) : r.cell!.value}</strong> {r.cell && <small>n={r.cell.n}</small>}</span>
     <span className="deep-count-bias">{!b || b.na || b.value === null ? <Chip tone="muted">{naText(b?.na)}</Chip> : <Chip tone={biasTone(b.value)}>{biasText(b.value)}</Chip>}</span>
    </div>;
   })}
  </ChartFrame>
 </div>;
}

/** Counts per code: one small-multiple card per code with Human vs selected combos and a bias chip per combo. */
export function CountBars({ codes, human, cells, bias, series, onSection }: { codes: string[]; human: CompareDeepDive['counts']['human']; cells: MetricCells; bias: CompareDeepDive['counts']['bias_pct']; series: DotSeries[]; onSection?: (code: string, node: HTMLElement | null) => void }) {
 return <div className="deep-counts">
  <div className="deep-grid">{codes.map(code => <section key={code} ref={node => onSection?.(code, node)}><CountCard code={code} human={human} cells={cells[code]} bias={bias[code]} series={series}/></section>)}</div>
  <Note>Counts are averages over the paired sessions. Bias chip: green within 10%, amber 10-20%, red over 20%.</Note>
 </div>;
}
