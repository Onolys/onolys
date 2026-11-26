import { Chip } from '../../ui/Chip';
import { ChartFrame } from '../../ui/ChartFrame';
import { ComboTag, SHAPES } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import { Axis, CHART_COLORS, CHART_GUTTER, comboColor, comboShape, linearScale, plotBox } from '../../ui/chart';
import type { CompareAnalysis, FrontierPoint } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import { layoutLabels } from './labelLayout';
import './costAccuracy.css';

const W = 640, H = 340;
type Status = 'frontier' | 'dominated' | 'unpriced' | 'unavailable' | 'failed';
interface Row { key: string; status: Status; cost: number | null; off: number | null; n: number | null; note: string }
const usd = (v: number) => `$${Number(v.toFixed(3))}`;
const unavailable = (reason?: string) => `n/a${reason ? ` - ${reason}` : ''}`;
const STATUS_LABEL: Record<Status, string> = { frontier: 'Frontier', dominated: 'Dominated', unpriced: 'Unpriced', unavailable: 'Unavailable', failed: 'Failed' };

/** Cost vs accuracy: ComboTag-shaped markers on visx scales, a dashed frontier from the server's frontier flags, failed/unpriced combos listed muted below (never plotted as $0). */
export function CostAccuracyScatter({ data, legend, failed }: { data: CompareAnalysis; legend: ComboLegendEntry[]; failed: FailedCombo[] }) {
 const failedAll = new Map(failed.filter(f => f.all).map(f => [f.combo_key, f]));
 const index = (key: string) => Math.max(0, legend.findIndex(e => e.combo.combo_key === key));
 const letter = (key: string) => legend.find(e => e.combo.combo_key === key)?.letter ?? key;
 const name = (key: string) => `${letter(key)}${data.skipped_combos.includes(key) ? ' (skipped)' : ''}`;
 const frontierKeys = new Set(data.frontier.points.map(p => p.combo_key));
 const plotted: FrontierPoint[] = [...data.frontier.points, ...data.frontier.dominated].filter(p => !failedAll.has(p.combo_key));
 const frontierLine = data.frontier.points.filter(p => !failedAll.has(p.combo_key)).sort((a, b) => a.cost_per_run_usd - b.cost_per_run_usd);

 const rows: Row[] = [];
 const seen = new Set<string>();
 const add = (row: Row) => { if (!seen.has(row.key)) { seen.add(row.key); rows.push(row); } };
 for (const f of failedAll.values()) add({ key: f.combo_key, status: 'failed', cost: null, off: null, n: null, note: `all runs failed: ${f.code}` });
 for (const p of plotted) add({ key: p.combo_key, status: frontierKeys.has(p.combo_key) ? 'frontier' : 'dominated', cost: p.cost_per_run_usd, off: p.count_error, n: p.n, note: '' });
 for (const p of data.frontier.unpriced) add({ key: p.combo_key, status: 'unpriced', cost: null, off: p.count_error, n: p.n, note: unavailable(p.na?.reason) });
 for (const p of data.frontier.unavailable) add({ key: p.combo_key, status: 'unavailable', cost: null, off: null, n: p.n, note: unavailable(p.na?.reason) });
 const notPlotted = rows.filter(r => r.cost === null);

 const box = plotBox(W, H);
 const maxX = Math.max(0, ...plotted.map(p => p.cost_per_run_usd)) || 1;
 const maxY = Math.max(0, ...plotted.map(p => p.count_error)) || 1;
 const x = linearScale({ domain: [0, maxX * 1.1], range: [box.left, box.left + box.width] });
 const y = linearScale({ domain: [0, maxY * 1.15], range: [box.top + box.height, box.top] });
 const labels = layoutLabels(plotted.map(p => ({ id: p.combo_key, px: x(p.cost_per_run_usd), py: y(p.count_error), w: Math.max(10, name(p.combo_key).length * 8), h: 14 })),
  { left: box.left, top: box.top, right: box.left + box.width, bottom: box.top + box.height });
 const step = frontierLine.map((p, i) => `${i === 0 ? 'M' : `H${x(p.cost_per_run_usd)}V`}${i === 0 ? `${x(p.cost_per_run_usd)},${y(p.count_error)}` : y(p.count_error)}`).join(' ');
 const gridY = y.ticks(5);

 const columns: Column<Row>[] = [
  { key: 'combo', header: 'Combo', value: r => letter(r.key), render: r => <ComboTag index={index(r.key)} letter={letter(r.key)} /> },
  { key: 'cost', header: 'Cost per run (USD)', value: r => r.cost, render: r => r.cost === null ? 'n/a' : `${usd(r.cost)} · n=${data.frontier.points.concat(data.frontier.dominated).find(p => p.combo_key === r.key)?.cost_n}` },
  { key: 'off', header: 'Count error', value: r => r.off, render: r => r.off === null ? 'n/a' : `${r.off} · n=${r.n}` },
  { key: 'status', header: 'Status', value: r => STATUS_LABEL[r.status], render: r => <>{STATUS_LABEL[r.status]}{r.note ? ` · ${r.note}` : ''}</> },
 ];
 const table = <DataTable ariaLabel="Cost vs accuracy" rows={rows} columns={columns} rowKey={r => r.key} rowTone={r => r.status === 'failed' ? 'danger' : undefined} searchLabel="Search combos" />;
 const chartLegend = legend.filter(e => plotted.some(p => p.combo_key === e.combo.combo_key)).map(e => <span key={e.combo.combo_key} className="ca-legend"><ComboTag index={index(e.combo.combo_key)} letter={e.letter} /> <span>{e.label}</span></span>);

 return <ChartFrame title="Cost vs accuracy" caption="Lower and further left is better; the dashed line joins combos no other combo beats on both axes." legend={chartLegend} table={table}>
  {plotted.length ? <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cost vs accuracy scatter" className="ca-svg">
   {gridY.map(t => <line key={t} x1={box.left} x2={box.left + box.width} y1={y(t)} y2={y(t)} stroke={CHART_COLORS.grid} strokeDasharray="3 4" />)}
   <Axis orientation="left" scale={y} tickValues={gridY} left={CHART_GUTTER.left} label="Count error (lower is better)" />
   <Axis orientation="bottom" scale={x} top={box.top + box.height} left={0} numTicks={5} tickFormat={usd} label="Cost per run (lower is better)" />
   {frontierLine.length > 1 && <path className="ca-frontier" data-frontier-combos={frontierLine.map(p => p.combo_key).join(',')} d={step} fill="none" stroke={CHART_COLORS.primary} strokeWidth={2} strokeDasharray="5 4" />}
   {plotted.map(p => {
    const frontier = frontierKeys.has(p.combo_key), i = index(p.combo_key), cx = x(p.cost_per_run_usd), cy = y(p.count_error);
    return <g key={p.combo_key} data-cost-point={p.combo_key} data-frontier={frontier} data-shape={comboShape(i)} transform={`translate(${cx - 8} ${cy - 8}) scale(1.33)`} color={comboColor(i)}>
     <title>{`${name(p.combo_key)}: cost ${p.cost_per_run_usd} USD, cost n=${p.cost_n}; Count error ${p.count_error}, n=${p.n}; ${frontier ? 'Frontier' : 'Dominated'}`}</title>
     <path d={SHAPES[comboShape(i)]} fill="currentColor" stroke={frontier ? CHART_COLORS.ink : 'none'} strokeWidth={frontier ? 0.8 : 0} fillOpacity={frontier ? 1 : 0.8} />
    </g>;
   })}
   {plotted.map((p, k) => <text key={p.combo_key} data-cost-label={p.combo_key} x={labels[k].x} y={labels[k].y + labels[k].h - 3} fill={comboColor(index(p.combo_key))} fontSize={12} fontWeight={700}>{name(p.combo_key)}</text>)}
  </svg> : <p className="ca-empty">No priced results available</p>}
  {notPlotted.length > 0 && <ul className="ca-excluded" aria-label="Not plotted">
   {notPlotted.map(r => <li key={r.key} data-status={r.status}><ComboTag index={index(r.key)} letter={letter(r.key)} />
    {r.status === 'failed' && <Chip tone="danger">failed</Chip>}
    <span>{r.status === 'failed' ? '' : `${name(r.key)}: `}{r.note}{r.off !== null ? ` · Count error ${r.off} · n=${r.n}` : r.n !== null ? ` · n=${r.n}` : ''}</span></li>)}
  </ul>}
 </ChartFrame>;
}
