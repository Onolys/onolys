import { useState, type ReactNode } from 'react';
import { ChartFrame } from '../../ui/ChartFrame';
import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import { Disclosure } from '../../ui/Disclosure';
import type { LineMetrics } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import '../deepDive.css';

export interface ConfusionPick { combo: string; code: string; metric: string }
interface Flat { human: string; predicted: string; lines: number }
const round = (value: number) => Number(value.toFixed(2));

function cellStyle(value: number, rowTotal: number, agree: boolean) {
 const share = rowTotal > 0 ? value / rowTotal : 0;
 if (value <= 0) return undefined;
 return agree ? { background: `rgba(23,91,66,${(0.15 + share * 0.55).toFixed(2)})`, color: share > 0.45 ? '#fff' : undefined } : { background: `rgba(180,83,9,${(0.1 + share * 0.5).toFixed(2)})` };
}

/** Confusion grid behind a toggle: human rows x combo columns as a CSS grid, switchable combo, a separate multi row, click opens matching lines. */
export function ConfusionGrid({ combos, series, onMatch, onSwitch, footer }: { combos: LineMetrics['combos']; series: DotSeries[]; onMatch: (pick: ConfusionPick) => void; onSwitch?: () => void; footer?: ReactNode }) {
 const [choice, setChoice] = useState<string>();
 const current = series.find(s => s.key === choice) ?? series[0];
 const data = current ? combos[current.key] : undefined;
 if (!current || !data) return null;
 const rows = Object.keys(data.confusion);
 const columns = [...new Set(Object.values(data.confusion).flatMap(row => Object.keys(row)))];
 const flat: Flat[] = [...rows.flatMap(human => columns.map(predicted => ({ human, predicted, lines: round(data.confusion[human][predicted] ?? 0) }))).filter(item => item.lines > 0), ...(data.multi ? [{ human: 'multi', predicted: 'multi', lines: round(data.multi) }] : [])];
 const twin: Column<Flat>[] = [
  { key: 'human', header: 'Human code', value: r => r.human },
  { key: 'predicted', header: `${current.letter} code`, value: r => r.predicted },
  { key: 'lines', header: 'Aligned lines', value: r => r.lines },
 ];
 const switcher = <div className="deep-toggles" role="group" aria-label="Confusion combo">
  {series.map(s => <button key={s.key} type="button" className={`deep-toggle${s.key === current.key ? ' is-on' : ''}`} aria-pressed={s.key === current.key} onClick={() => { setChoice(s.key); onSwitch?.(); }}><ComboTag index={s.index} letter={s.letter}/></button>)}
 </div>;
 const legend = <><span className="deep-legend-item"><span className="deep-swatch deep-agree" aria-hidden="true"/>agree (human = combo)</span><span className="deep-legend-item"><span className="deep-swatch deep-confused" aria-hidden="true"/>confused (open a cell to see lines)</span></>;
 return <section className="deep-confusion-section" aria-label="Confusion">
  <Disclosure label="Show confusion grid">
   <ChartFrame title={`Confusion · combo ${current.letter}`} caption={`Rows are human codes, columns are ${current.letter}'s codes; ${data.aligned} aligned lines over ${data.n} sessions.`} legend={legend}
    table={<DataTable rows={flat} columns={twin} rowKey={r => `${r.human}/${r.predicted}`} ariaLabel="Confusion data" searchLabel="Search codes"/>}>
    {switcher}
    <div className="deep-confusion" role="table" aria-label="Confusion grid" style={{ ['--cols' as string]: columns.length }}>
     <div role="row" className="deep-conf-row"><span role="columnheader" className="deep-conf-head deep-conf-corner">Human / {current.letter}</span>{columns.map(c => <span key={c} role="columnheader" className="deep-conf-head">{c}</span>)}</div>
     {rows.map(human => {
      const total = columns.reduce((sum, c) => sum + (data.confusion[human][c] ?? 0), 0);
      return <div key={human} role="row" className="deep-conf-row"><span role="rowheader" className="deep-conf-head deep-conf-rowhead">{human}</span>{columns.map(predicted => {
       const value = round(data.confusion[human][predicted] ?? 0);
       return <span key={predicted} role="cell" className="deep-conf-cell"><button type="button" data-confusion-value={value} disabled={value === 0} style={cellStyle(value, total, human === predicted)} aria-label={`Human ${human}, ${current.letter} ${predicted}: ${value}`} onClick={() => onMatch({ combo: current.key, code: human, metric: predicted })}>{value}</button></span>;
      })}</div>;
     })}
     <div role="row" className="deep-conf-row deep-conf-multi"><span role="rowheader" className="deep-conf-head deep-conf-rowhead">multi (multiple codes on either side)</span><span role="cell" className="deep-conf-cell"><button type="button" data-confusion-multi data-confusion-value={round(data.multi)} disabled={!data.multi} aria-label={`Multi-code lines, ${current.letter}: ${round(data.multi)}`} onClick={() => onMatch({ combo: current.key, code: 'multi', metric: 'multi' })}>{round(data.multi)}</button></span></div>
    </div>
    <Chip tone="info">Multi-code lines are kept in their own row so totals match.</Chip>
    {footer}
   </ChartFrame>
  </Disclosure>
 </section>;
}
