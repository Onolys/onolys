// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareCell, CompareDeepDive } from '../compareApi';
import deepFixture from '../fixtures/deepDive.json';
import { GlobalsDotPlot } from './GlobalsDotPlot';
import { dotPlotLayout, LABEL_CHAR_PX, SYMBOL_SIZE, type DotSeries } from './dotPlotLayout';
afterEach(cleanup);
const deep = () => structuredClone(deepFixture) as CompareDeepDive;
const series: DotSeries[] = [{ key: 'a', letter: 'A', index: 0, label: 'A-label' }, { key: 'b', letter: 'B', index: 1, label: 'B-label' }, { key: 'c', letter: 'C', index: 2, label: 'C-label' }];
const rows = [
  { session_id: 'gi', human: 4, values: { a: [4, 4], b: [4], c: [5] } },
  { session_id: 'a-very-long-session-hash-3f9c1d2b7e', human: 3, values: { a: [3], b: [2, 4], c: [] } },
  { session_id: 's03', human: null, values: { a: [1], b: [1, 1, 1], c: [1] } },
];

it('reserves a label gutter left of the plot; labels and lane letters sit inside the gutter, never over the plot', () => {
  const l = dotPlotLayout({ rows, series });
  expect(l.gutter).toBeGreaterThan(0);
  expect(l.plotLeft).toBeGreaterThan(l.gutter);
  for (const row of l.rows) {
    expect(row.labelX + row.label.length * LABEL_CHAR_PX).toBeLessThan(row.lanes[0].letterX - 4); // label ends before the lane letters
    expect(row.lanes[0].letterX).toBeLessThanOrEqual(l.gutter);
  }
  expect(l.rows[1].label).not.toBe(rows[1].session_id); // long hash truncated, full id kept for the tooltip
  expect(l.rows[1].labelFull).toBe(rows[1].session_id);
  expect(l.rows[1].label.endsWith('…')).toBe(true);
});
it('draws axis ticks 1-5 above the first row only, inside the plot', () => {
  const l = dotPlotLayout({ rows, series });
  expect(l.ticks.map(t => t.value)).toEqual([1, 2, 3, 4, 5]);
  for (const t of l.ticks) { expect(t.labelY).toBeLessThan(l.rows[0].top); expect(t.x).toBeGreaterThanOrEqual(l.plotLeft); expect(t.x).toBeLessThanOrEqual(l.width); }
});
it('gives each series its own lane per row and no two symbols in a row collide, even equal repeats', () => {
  const l = dotPlotLayout({ rows, series });
  for (const row of l.rows) {
    const laneYs = row.lanes.map(lane => lane.y);
    expect(new Set(laneYs).size).toBe(laneYs.length);
    const all = [...(row.human ? [row.human] : []), ...row.lanes.flatMap(lane => lane.symbols)];
    for (const s of all) { expect(s.y).toBeGreaterThan(row.top); expect(s.y).toBeLessThan(row.top + row.height); }
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
      const apart = Math.abs(all[i].x - all[j].x) >= SYMBOL_SIZE || Math.abs(all[i].y - all[j].y) >= SYMBOL_SIZE;
      expect(apart, `${row.session_id} symbols ${i}/${j}`).toBe(true);
    }
  }
  expect(l.rows[0].lanes[0].symbols).toHaveLength(2);
  expect(l.rows[2].human).toBeNull();
});
it('places symbols at their rating on the 1-5 scale (human line x equals human symbol x)', () => {
  const l = dotPlotLayout({ rows, series });
  const r = l.rows[0];
  expect(r.human!.x).toBe(l.ticks[3].x);
  expect(r.lanes[2].symbols[0].x).toBe(l.ticks[4].x);
});

const cell = (over: Partial<CompareCell>): CompareCell => ({ value: null, off: 0.4, bias: 0, n: 2, of: 2, repeats: 2, within_tolerance: true, best: false, na: null, within_1: 1, ...over });
it('renders a card per global with title, one-sentence caption, legend, chips from the fixture, and svg dots', () => {
  const data = deep();
  const keys = data.combos.map(c => c.combo_key);
  const dp = data.globals.dots.filter(d => d.metric === 'cct');
  const s: DotSeries[] = keys.map((key, index) => ({ key, letter: String.fromCharCode(65 + index), index, label: key }));
  const view = render(<GlobalsDotPlot metric="cct" title="Cultivating change talk ratings" dots={dp} series={s} cells={data.globals.cells.cct} />);
  expect(screen.getByRole('heading', { name: 'Cultivating change talk ratings' })).toBeTruthy();
  expect(screen.getByText(/hollow circle = human/)).toBeTruthy();
  const legend = view.container.querySelector('.ui-chart-legend')!;
  expect(within(legend as HTMLElement).getByText('Human')).toBeTruthy();
  expect(legend.textContent).toContain(keys[0]);
  const chips = view.container.querySelectorAll('.deep-miss-chip');
  expect(chips).toHaveLength(2);
  const cc = data.globals.cells.cct[keys[0]];
  expect(chips[0].textContent).toContain(`miss ${cc.off}`);
  expect(chips[0].textContent).toContain(`±1 ${Math.round((cc.within_1 ?? 0) * 100)}%`);
  expect(view.container.querySelector('svg[role="img"][aria-label^="Cultivating change talk"]')).toBeTruthy();
  expect(view.container.querySelectorAll('[data-global-dot]').length).toBe(dp.reduce((n, d) => n + d.values.length, 0) + new Set(dp.filter(d => d.human !== null).map(d => d.session_id)).size);
});
it('shows unavailable combos as a muted chip with the server reason instead of plain n/a text', () => {
  const data = deep(); const keys = data.combos.map(c => c.combo_key);
  const s: DotSeries[] = keys.map((key, index) => ({ key, letter: String.fromCharCode(65 + index), index, label: key }));
  const cells = { [keys[0]]: cell({ off: null, within_1: undefined, n: 0, of: 1, repeats: 0, na: { reason: 'no completed runs' } }), [keys[1]]: cell({}) };
  const view = render(<GlobalsDotPlot metric="cct" title="T" dots={[]} series={s} cells={cells} />);
  const chips = view.container.querySelectorAll('.deep-miss-chip');
  expect(chips[0].textContent).toContain('no completed runs');
  expect(chips[0].textContent).not.toMatch(/paired 0 of 1/);
  expect(chips[0].getAttribute('title')).toContain('paired 0 of 1');
});
it('keeps the data table behind Show data and lists repeats individually', () => {
  const data = deep(); const keys = data.combos.map(c => c.combo_key);
  const s: DotSeries[] = keys.map((key, index) => ({ key, letter: String.fromCharCode(65 + index), index, label: key }));
  render(<GlobalsDotPlot metric="cct" title="T" dots={data.globals.dots.filter(d => d.metric === 'cct')} series={s} cells={data.globals.cells.cct} />);
  expect(screen.queryByRole('table')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
  const table = screen.getByRole('table', { name: 'cct ratings' });
  expect(table.textContent).toContain('4, 4');
});
