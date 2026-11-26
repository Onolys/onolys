// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { LineMetrics } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import { PrfTable } from './PrfTable';
afterEach(cleanup);
const series: DotSeries[] = [{ key: 'a', letter: 'A', index: 0, label: 'A-label' }, { key: 'b', letter: 'B', index: 1, label: 'B-label' }];
const combo = (per_code: LineMetrics['combos'][string]['per_code']): LineMetrics['combos'][string] => ({ lane: null, n: 5, repeats: 2, aligned: 40, per_code, macro_f1: null, line_accuracy: null, confusion: {}, multi: 0 });
const lines: LineMetrics = {
  missing: null, codes_labeled: ['q', 'sr', 'cr'], dataset_notes: ['Gold labels cover 3 of 10 codes.'],
  combos: {
    a: combo({ q: { p: 0.92, r: 0.9, f1: 0.91 }, sr: { p: 0.7, r: 0.64, f1: 0.5 }, cr: { p: null, r: null, f1: null } }),
    b: combo({ q: { p: 0.95, r: 0.93, f1: 0.25 }, sr: { p: 0.62, r: 0.69, f1: 0.65 }, cr: { p: null, r: null, f1: null } }),
  },
};
const codes = (view: { container: HTMLElement }) => [...view.container.querySelectorAll('tbody tr')].map(tr => tr.querySelector('td')!.textContent);

it('shows one row per code with an F1 bar sized by F1 and P/R as sub-text, visible by default', () => {
  const view = render(<PrfTable lines={lines} series={series} />);
  const row = view.container.querySelector('[data-prf-row="q"]')!.closest('tr')!;
  const bars = [...row.querySelectorAll<HTMLElement>('[data-f1-bar]')].map(b => [b.dataset.f1Bar, b.style.width]);
  expect(bars).toEqual([['a', '91%'], ['b', '25%']]);
  expect(row.textContent).toContain('0.91');
  expect(row.textContent).toContain('P 0.92 · R 0.90');
  expect(screen.getByRole('table', { name: 'Line agreement' })).toBeTruthy();
});
it('shows n/a without a bar when a code has no precision, recall or F1', () => {
  const view = render(<PrfTable lines={lines} series={series} />);
  const row = view.container.querySelector('[data-prf-row="cr"]')!.closest('tr')!;
  expect(row.querySelectorAll('[data-f1-bar]').length).toBe(0);
  expect(row.textContent).toContain('n/a');
});
it('names the labeled-code count, dataset notes and per-combo sessions and aligned lines', () => {
  render(<PrfTable lines={lines} series={series} />);
  expect(screen.getByText('3 of 10 codes labeled')).toBeTruthy();
  expect(screen.getByText('Gold labels cover 3 of 10 codes.')).toBeTruthy();
  expect(screen.getByText(/A: n=5 sessions · 40 aligned lines · 2 repeats/)).toBeTruthy();
});
it('sorts by a combo F1 column', () => {
  const view = render(<PrfTable lines={lines} series={series} />);
  const header = screen.getByRole('columnheader', { name: /A · F1/ });
  fireEvent.click(header);
  expect(header.getAttribute('aria-sort')).toBe('ascending');
  expect(codes(view)[0]).toBe('sr');
  fireEvent.click(header);
  expect(header.getAttribute('aria-sort')).toBe('descending');
  expect(codes(view)[0]).toBe('q');
  fireEvent.click(screen.getByRole('columnheader', { name: /B · F1/ }));
  expect(within(view.container).getAllByRole('columnheader')[2].getAttribute('aria-sort')).toBe('ascending');
});
