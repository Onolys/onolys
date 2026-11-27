import { useState } from 'react';
import { Chip } from '../../ui/Chip';
import { ChartFrame } from '../../ui/ChartFrame';
import { ComboTag, SHAPES } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import { Axis, CHART_COLORS, CHART_GUTTER, comboColor, comboShape, linearScale, plotBox } from '../../ui/chart';
import type { CompareAnalysis } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import { sessionLabel } from '../sessionLabel';
import './errorVsLength.css';

const W = 640, H = 300;
type Point = CompareAnalysis['error_vs_length'][number];
type Axis = 'turns' | 'words';
const AXIS_LABEL: Record<Axis, string> = { turns: 'Turns', words: 'Words' };

/** Error vs interview length: one connected series per combo (points sorted by the chosen length), Turns/Words switch, failed combos listed muted and never plotted. Values are the server's; scales only place them. */
export function ErrorVsLength({ data, legend, failed }: { data: CompareAnalysis; legend: ComboLegendEntry[]; failed: FailedCombo[] }) {
 const [axis, setAxis] = useState<Axis>('turns');
 const failedAll = new Map(failed.filter(f => f.all).map(f => [f.combo_key, f]));
 const index = (key: string) => Math.max(0, legend.findIndex(e => e.combo.combo_key === key));
 const letter = (key: string) => legend.find(e => e.combo.combo_key === key)?.letter ?? key;
 const name = (key: string) => `${letter(key)}${data.skipped_combos.includes(key) ? ' (skipped)' : ''}`;
 const points = data.error_vs_length.filter(p => !failedAll.has(p.combo_key));
 const keys = [...new Set(points.map(p => p.combo_key))];
 const series = keys.map(key => ({ key, points: points.filter(p => p.combo_key === key).sort((a, b) => a[axis] - b[axis]) }));

 const box = plotBox(W, H);
 const xs = points.map(p => p[axis]);
 const minX = Math.min(...xs), maxX = Math.max(...xs);
 const pad = (maxX - minX) * 0.06 || 1;
 const maxY = Math.max(0, ...points.map(p => p.off)) || 1;
 const x = linearScale({ domain: [Math.max(0, minX - pad), maxX + pad], range: [box.left, box.left + box.width] });
 const y = linearScale({ domain: [0, maxY * 1.15], range: [box.top + box.height, box.top] });
 const yTicks = y.ticks(5);

 const columns: Column<Point>[] = [
  { key: 'session', header: 'Session', value: p => sessionLabel(data.session_labels, p.session_id) },
  { key: 'combo', header: 'Combo', value: p => letter(p.combo_key), render: p => <ComboTag index={index(p.combo_key)} letter={letter(p.combo_key)} /> },
  { key: 'len', header: AXIS_LABEL[axis], value: p => p[axis] },
  { key: 'off', header: 'Count error', value: p => p.off },
  { key: 'n', header: 'n', value: p => p.n },
  { key: 'repeats', header: 'Repeats', value: p => p.repeats },
 ];
 const table = <DataTable ariaLabel="Error vs length" rows={points} columns={columns} rowKey={p => `${p.session_id}-${p.combo_key}`} searchLabel="Search sessions" />;
 const toggle = <div className="evl-toggle" role="group" aria-label="Length axis">{(['turns', 'words'] as const).map(a => <button type="button" key={a} aria-pressed={axis === a} onClick={() => setAxis(a)}>{AXIS_LABEL[a]}</button>)}</div>;
 const chartLegend = keys.map(key => <span key={key} className="evl-legend"><ComboTag index={index(key)} letter={letter(key)} /> <span>{legend.find(e => e.combo.combo_key === key)?.label ?? key}</span></span>);

 return <ChartFrame title="Error vs interview length" caption="One point per session and combo; lines join each combo's sessions from shortest to longest." legend={chartLegend} table={table}>
  {toggle}
  {points.length ? <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Error vs length scatter" className="evl-svg">
   {yTicks.map(t => <line key={t} x1={box.left} x2={box.left + box.width} y1={y(t)} y2={y(t)} stroke={CHART_COLORS.grid} strokeDasharray="3 4" />)}
   <Axis orientation="left" scale={y} tickValues={yTicks} left={CHART_GUTTER.left} label="Count error (lower is better)" />
   <Axis orientation="bottom" scale={x} top={box.top + box.height} left={0} numTicks={6} label={`Interview length (${axis})`} />
   {series.map(s => <g key={s.key} data-length-series={s.key} color={comboColor(index(s.key))}>
    {s.points.length > 1 && <polyline points={s.points.map(p => `${x(p[axis])},${y(p.off)}`).join(' ')} fill="none" stroke="currentColor" strokeOpacity={0.4} strokeWidth={2} />}
    {s.points.map(p => <g key={p.session_id} data-length-point={`${p.session_id}-${p.combo_key}`} data-x={p[axis]} data-shape={comboShape(index(s.key))} transform={`translate(${x(p[axis]) - 8} ${y(p.off) - 8}) scale(1.33)`}>
     <title>{`${sessionLabel(data.session_labels, p.session_id)}, ${name(p.combo_key)}: ${p[axis]} ${axis}, Count error ${p.off}, n=${p.n}, ${p.repeats} repeats`}</title>
     <path d={SHAPES[comboShape(index(s.key))]} fill="currentColor" fillOpacity={0.85} />
    </g>)}
   </g>)}
  </svg> : <p className="evl-empty">No session length results available</p>}
  {failedAll.size > 0 && <ul className="evl-excluded" aria-label="Not plotted">
   {[...failedAll.values()].map(f => <li key={f.combo_key}><ComboTag index={index(f.combo_key)} letter={letter(f.combo_key)} /><Chip tone="danger">failed</Chip><span>all runs failed: {f.code}</span></li>)}
  </ul>}
 </ChartFrame>;
}
