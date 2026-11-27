import { Chip } from '../../ui/Chip';
import { ChartFrame } from '../../ui/ChartFrame';
import { CHART_COLORS, comboColor, comboShape } from '../../ui/chart/theme';
import { ComboTag, SHAPES } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import type { CompareCell, CompareDeepDive } from '../compareApi';
import { sessionLabel, type SessionLabels } from '../sessionLabel';
import { dotPlotLayout, ROW_PAD, SYMBOL_SIZE, type DotRowInput, type DotSeries } from './dotPlotLayout';
import '../deepDive.css';

type Dot = CompareDeepDive['globals']['dots'][number];
const naText = (cell: CompareCell | undefined) => (cell?.na ? `n/a - ${cell.na.reason}` : 'n/a');
const pairedText = (cell: CompareCell) => `paired ${cell.n} of ${cell.of} · ${cell.repeats} repeats`;

function MissChip({ s, cell }: { s: DotSeries; cell: CompareCell | undefined }) {
 const usable = cell && !cell.na && cell.off !== null;
 return <span className="deep-miss-chip" title={cell ? pairedText(cell) : undefined}>
  <Chip tone={usable ? 'neutral' : 'muted'} icon={<ComboTag index={s.index} letter={s.letter}/>}>
   {usable ? `miss ${cell.off} · ±1 ${cell.within_1 === undefined ? 'n/a' : `${Math.round(cell.within_1 * 100)}%`}` : naText(cell)}
  </Chip>
 </span>;
}

/** One card per global: dot plot (session rows, one lane per series), legend, avg miss / within ±1 chips, data table behind "Show data". */
export function GlobalsDotPlot({ metric, title, dots, series, cells, labels }: { metric: string; title: string; dots: Dot[]; series: DotSeries[]; cells: Record<string, CompareCell>; labels?: SessionLabels }) {
 const sessions = [...new Set(dots.map(dot => dot.session_id))];
 const rows: DotRowInput[] = sessions.map(session => ({
  session_id: session,
  label: sessionLabel(labels, session),
  human: dots.find(dot => dot.session_id === session)?.human ?? null,
  values: Object.fromEntries(series.map(s => [s.key, dots.find(dot => dot.session_id === session && dot.combo_key === s.key)?.values ?? []])),
 }));
 const layout = dotPlotLayout({ rows, series });
 const columns: Column<DotRowInput>[] = [
  { key: 'session', header: 'Session', value: row => row.label ?? row.session_id },
  { key: 'human', header: 'Human', value: row => row.human ?? 'n/a' },
  ...series.map((s): Column<DotRowInput> => ({ key: s.key, header: s.letter, value: row => {
   const dot = dots.find(d => d.session_id === row.session_id && d.combo_key === s.key);
   return dot?.values.length ? `${dot.values.join(', ')} · n=${dot.n} · ${dot.repeats} repeats` : naText(cells[s.key]);
  } })),
 ];
 const legend = <>
  <span className="deep-legend-item"><span className="deep-human-swatch" aria-hidden="true"/>Human</span>
  {series.map(s => <span className="deep-legend-item" key={s.key}><ComboTag index={s.index} letter={s.letter}/>{s.label}</span>)}
 </>;
 return <div className="deep-dot-card">
  <ChartFrame title={title} caption="Rating 1-5 per interview: hollow circle = human, shapes = combos, dashed line marks the human rating." legend={legend}
   table={<DataTable rows={rows} columns={columns} rowKey={row => row.session_id} ariaLabel={`${metric} ratings`} searchLabel="Search sessions"/>}>
   {rows.length === 0 ? <p className="deep-empty">No paired ratings for the selected combos.</p> :
    <svg className="deep-dot-svg" viewBox={`0 0 ${layout.width} ${layout.height}`} role="img" aria-label={`${title}: human and combo ratings per session`}>
     {layout.ticks.map(t => <g key={t.value}><line x1={t.x} x2={t.x} y1={layout.rows[0].top} y2={layout.height - 6} stroke={CHART_COLORS.grid} strokeDasharray={t.value === 1 || t.value === 5 ? undefined : '3 4'}/>
      <text x={t.x} y={t.labelY} textAnchor="middle" fontSize="12" fill={CHART_COLORS.muted}>{t.value}</text></g>)}
     {layout.rows.map((row, i) => <g key={row.session_id} data-session={row.session_id}>
      {i % 2 === 0 && <rect x="0" y={row.top} width={layout.width} height={row.height} fill="#f7f9f9" opacity=".8"/>}
      <text x={row.labelX} y={row.labelY} dy=".35em" fontSize="13" fontWeight="600" fill={CHART_COLORS.ink}>{row.label}<title>{row.labelFull}</title></text>
      {row.lanes.map(lane => <text key={lane.key} x={lane.letterX} y={lane.y} dy=".35em" textAnchor="end" fontSize="10" fontWeight="700" fill={comboColor(lane.index)}>{lane.letter}</text>)}
      {row.human && <line x1={row.human.x} x2={row.human.x} y1={row.top + ROW_PAD / 2} y2={row.top + row.height - ROW_PAD / 2} stroke={CHART_COLORS.ink} strokeOpacity=".35" strokeDasharray="2 3"/>}
      {row.human && <circle data-global-dot="human" cx={row.human.x} cy={row.human.y} r={SYMBOL_SIZE / 2} fill="#fff" stroke={CHART_COLORS.ink} strokeWidth="2"><title>{`${row.labelFull}, Human: ${row.human.value}`}</title></circle>}
      {row.lanes.flatMap(lane => lane.symbols.map(sym => <path key={`${lane.key}-${sym.repeat}`} data-global-dot={lane.key} d={SHAPES[comboShape(lane.index)]} transform={`translate(${sym.x - SYMBOL_SIZE / 2} ${sym.y - SYMBOL_SIZE / 2}) scale(${SYMBOL_SIZE / 12})`} fill={comboColor(lane.index)}><title>{`${row.labelFull}, ${lane.letter}, repeat ${sym.repeat + 1}: ${sym.value}`}</title></path>))}
     </g>)}
    </svg>}
   <div className="deep-miss-chips">{series.map(s => <MissChip key={s.key} s={s} cell={cells[s.key]}/>)}</div>
  </ChartFrame>
 </div>;
}
