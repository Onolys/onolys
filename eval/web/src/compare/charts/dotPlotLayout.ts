import { SCORE_TICKS, scoreScale } from '../../ui/chart/scales';

export interface DotSeries { key: string; letter: string; index: number; label: string }
export interface DotRowInput { session_id: string; human: number | null; values: Record<string, number[]> }
export interface Symbol { x: number; y: number; value: number; repeat: number }

/** Layout constants in viewBox px. The gutter (labels + lane letters) is fixed; the plot starts to its right. */
export const WIDTH = 560;
export const GUTTER = 128;
export const PLOT_LEFT = 136;
export const SYMBOL_SIZE = 9;
export const LANE = 13;
export const ROW_PAD = 7;
export const AXIS_TOP = 28;
export const LABEL_CHAR_PX = 7.5;
const LABEL_MAX_CHARS = 13;
const truncate = (text: string) => (text.length > LABEL_MAX_CHARS ? `${text.slice(0, LABEL_MAX_CHARS - 1)}…` : text);

export interface DotLane { key: string; letter: string; index: number; y: number; letterX: number; symbols: Symbol[] }
export interface DotRowLayout { session_id: string; label: string; labelFull: string; labelX: number; labelY: number; top: number; height: number; human: Symbol | null; lanes: DotLane[] }
export interface DotPlotLayout { width: number; height: number; gutter: number; plotLeft: number; ticks: { value: number; x: number; labelY: number }[]; rows: DotRowLayout[] }

/** Pure geometry: one row per session, one horizontal lane per series (Human first), so symbols of different series never share a lane. Repeats of one series with the same rating are spread sideways. */
export function dotPlotLayout({ rows, series, width = WIDTH }: { rows: DotRowInput[]; series: DotSeries[]; width?: number }): DotPlotLayout {
 const scale = scoreScale(PLOT_LEFT + 10, width - 20);
 const rowHeight = ROW_PAD * 2 + (series.length + 1) * LANE;
 const laneY = (top: number, lane: number) => top + ROW_PAD + LANE * (lane + 0.5);
 const placed = rows.map((row, i): DotRowLayout => {
  const top = AXIS_TOP + i * rowHeight;
  const lanes = series.map((s, j): DotLane => {
   const values = row.values[s.key] ?? [];
   const seen = new Map<number, number>();
   const totals = new Map<number, number>();
   values.forEach(v => totals.set(v, (totals.get(v) ?? 0) + 1));
   const symbols = values.map((value, repeat): Symbol => {
    const k = seen.get(value) ?? 0; seen.set(value, k + 1);
    const spread = ((k - ((totals.get(value) ?? 1) - 1) / 2)) * (SYMBOL_SIZE + 1);
    return { x: scale(value) + spread, y: laneY(top, j + 1), value, repeat };
   });
   return { key: s.key, letter: s.letter, index: s.index, y: laneY(top, j + 1), letterX: GUTTER - 6, symbols };
  });
  return { session_id: row.session_id, label: truncate(row.session_id), labelFull: row.session_id, labelX: 8, labelY: top + rowHeight / 2, top, height: rowHeight,
   human: row.human === null ? null : { x: scale(row.human), y: laneY(top, 0), value: row.human, repeat: 0 }, lanes };
 });
 return { width, height: AXIS_TOP + rows.length * rowHeight + 6, gutter: GUTTER, plotLeft: PLOT_LEFT,
  ticks: SCORE_TICKS.map(value => ({ value, x: scale(value), labelY: 16 })), rows: placed };
}
