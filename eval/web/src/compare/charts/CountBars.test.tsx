// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareCell, ValueCell } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import { CountBars, biasText, biasTone } from './CountBars';
afterEach(cleanup);
const series: DotSeries[] = [{ key: 'a', letter: 'A', index: 0, label: 'A-label' }, { key: 'b', letter: 'B', index: 1, label: 'B-label' }];
const cell = (value: number | null, over: Partial<CompareCell> = {}): CompareCell => ({ value, off: 0, bias: 0, n: 5, of: 5, repeats: 2, within_tolerance: null, best: false, na: null, ...over });
const bias = (value: number | null, na: ValueCell['na'] = null): ValueCell => ({ value, n: 5, na });
const human = { q: { value: 100, min: 90, max: 110, n: 5, na: null } };
const props = (over: Partial<Parameters<typeof CountBars>[0]> = {}) => ({
  codes: ['q'], human, series,
  cells: { q: { a: cell(50), b: cell(100) } }, bias: { q: { a: bias(-50), b: bias(0) } }, ...over,
});

it('renders one card per code with Human and a bar per combo, widths proportional to the largest count', () => {
  const view = render(<CountBars {...props({ codes: ['q', 'r'], human: { ...human, r: { value: 4, min: 4, max: 4, n: 5, na: null } }, cells: { q: { a: cell(50), b: cell(100) }, r: { a: cell(2), b: cell(4) } }, bias: { q: { a: bias(-50), b: bias(0) }, r: { a: bias(-50), b: bias(0) } } })} />);
  expect(view.container.querySelectorAll('.ui-chart-frame').length).toBe(2);
  const q = view.container.querySelector('[data-count-card="q"]')!;
  const widths = [...q.querySelectorAll<HTMLElement>('[data-count-fill]')].map(f => [f.dataset.countFill, f.style.width]);
  expect(widths).toEqual([['human', '100%'], ['a', '50%'], ['b', '100%']]);
  const r = view.container.querySelector('[data-count-card="r"]')!;
  expect([...r.querySelectorAll<HTMLElement>('[data-count-fill]')].map(f => f.style.width)).toEqual(['100%', '50%', '100%']);
});
it('shows the counts and n for Human and each combo', () => {
  const view = render(<CountBars {...props()} />);
  const row = view.container.querySelector('[data-human-count="q"]')!;
  expect(row.textContent).toContain('Human');
  expect(row.textContent).toContain('100');
  expect(row.textContent).toContain('n=5');
  const rows = view.container.querySelectorAll('.deep-count-row');
  expect(rows[1].textContent).toContain('50');
  expect(rows[1].textContent).toContain('n=5');
});
it('maps bias to tone: green up to 10%, amber 10-20%, red above 20%', () => {
  expect([0, 5, 10, 10.4].map(biasTone)).toEqual(['success', 'success', 'success', 'success']);
  expect([11, -15, 20, 20.4].map(biasTone)).toEqual(['warning', 'warning', 'warning', 'warning']);
  expect([21, -50, 20.6].map(biasTone)).toEqual(['danger', 'danger', 'danger']);
  expect(biasTone(null)).toBe('muted');
});
it('words the bias chip with direction and percent, never colour alone', () => {
  expect(biasText(-21)).toBe('under-counts 21%');
  expect(biasText(11.2)).toBe('over-counts 11%');
  expect(biasText(0)).toBe('no count bias');
  const view = render(<CountBars {...props({ bias: { q: { a: bias(-21), b: bias(11) } } })} />);
  const chips = [...view.container.querySelectorAll('.ui-chip')];
  expect(chips.map(c => c.textContent)).toEqual(['under-counts 21%', 'over-counts 11%']);
  expect(chips.map(c => c.className)).toEqual(['ui-chip ui-chip-danger', 'ui-chip ui-chip-warning']);
  expect(chips[0].querySelector('svg')).toBeTruthy();
});
it('keeps the server reason for an unavailable bias or count', () => {
  render(<CountBars {...props({ cells: { q: { a: cell(null, { na: { reason: 'human count is zero' } }), b: cell(100) } }, bias: { q: { a: bias(null, { reason: 'human count is zero' }), b: bias(0) } } })} />);
  expect(screen.getAllByText(/n\/a - human count is zero/).length).toBeGreaterThan(0);
});
it('keeps the data table behind Show data and has one muted note', () => {
  const view = render(<CountBars {...props()} />);
  expect(screen.queryByRole('table', { name: 'q counts' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
  expect(screen.getByRole('table', { name: 'q counts' }).textContent).toContain('paired 5 of 5 · 2 repeats');
  expect(view.container.querySelectorAll('.deep-counts > .ui-note').length).toBe(1);
});
