// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareCell } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import { MissBuckets } from './MissBuckets';
afterEach(cleanup);
const series: DotSeries[] = [{ key: 'a', letter: 'A', index: 0, label: 'A-label' }, { key: 'b', letter: 'B', index: 1, label: 'B-label' }];
const cell = (over: Partial<CompareCell> = {}): CompareCell => ({ value: null, off: 0.5, bias: 0, n: 2, of: 2, repeats: 2, within_tolerance: null, best: false, na: null, within_1: 0.75, buckets: { same: 0.5, off1: 0.25, off2plus: 0.25 }, ...over });
const globals = [{ metric: 'cct', title: 'Cultivating change talk', cells: { a: cell(), b: cell({ off: null, na: { reason: 'no completed runs' }, buckets: undefined, within_1: undefined, n: 0 }) } }];
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Show miss-bucket bars' }));

it('is collapsed by default and opens on request', () => {
  const view = render(<MissBuckets globals={globals} series={series} />);
  expect(view.container.querySelector('.deep-stack')).toBeNull();
  expect(screen.getByRole('button', { name: 'Show miss-bucket bars' }).getAttribute('aria-expanded')).toBe('false');
  open();
  expect(view.container.querySelectorAll('.deep-stack').length).toBe(1);
});
it('sizes segments in proportion to shares and prints percent text, avg miss and within ±1', () => {
  const view = render(<MissBuckets globals={globals} series={series} />); open();
  const segs = [...view.container.querySelectorAll<HTMLElement>('.deep-stack [data-bucket]')];
  expect(segs.map(s => s.dataset.bucket)).toEqual(['same', 'off1', 'off2plus']);
  expect(segs.map(s => s.style.width)).toEqual(['50%', '25%', '25%']);
  expect(segs.map(s => s.textContent)).toEqual(['50%', '25%', '25%']);
  const bar = view.container.querySelector('.deep-stack')!;
  expect(bar.getAttribute('aria-label')).toBe('A: same 50%, off by 1 25%, off by 2+ 25%');
  const row = bar.closest('.deep-bucket-row') as HTMLElement;
  expect(row.textContent).toContain('miss 0.5');
  expect(row.textContent).toContain('within ±1: 75%');
});
it('shows a legend with text for each bucket and a chip with the reason for an unavailable combo', () => {
  render(<MissBuckets globals={globals} series={series} />); open();
  const legend = screen.getByLabelText('Miss bucket legend');
  expect(legend.textContent).toMatch(/same.*off by 1.*off by 2\+/);
  expect(screen.getByText(/no completed runs/)).toBeTruthy();
});
it('keeps the data table behind Show data once open', () => {
  render(<MissBuckets globals={globals} series={series} />); open();
  expect(screen.queryByRole('table', { name: 'cct misses' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
  expect(screen.getByRole('table', { name: 'cct misses' }).textContent).toContain('0.5');
  expect(screen.getByRole('table', { name: 'cct misses' }).textContent).toContain('50%');
});
