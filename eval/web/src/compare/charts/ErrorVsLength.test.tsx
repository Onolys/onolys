// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareAnalysis } from '../compareApi';
import analysis from '../fixtures/analysis.json';
import { ErrorVsLength } from './ErrorVsLength';
afterEach(cleanup);
const base = () => structuredClone(analysis) as CompareAnalysis;
const legendFor = (data: CompareAnalysis) => data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
const noFail: { combo_key: string; code: string; runs: number; all: boolean }[] = [];

it('draws one connected series per combo with server values', () => {
 const data = base();
 const { container } = render(<ErrorVsLength data={data} legend={legendFor(data)} failed={noFail} />);
 const series = [...container.querySelectorAll('[data-length-series]')];
 expect(series.map(s => s.getAttribute('data-length-series'))).toEqual(data.combos.map(c => c.combo_key));
 for (const s of series) { expect(s.querySelectorAll('[data-length-point]')).toHaveLength(2); expect(s.querySelector('polyline')).toBeTruthy(); }
 expect(screen.getByRole('img', { name: 'Error vs length scatter' })).toBeTruthy();
 expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
});

it('switches the x values between Turns and Words', () => {
 const data = base();
 const { container } = render(<ErrorVsLength data={data} legend={legendFor(data)} failed={noFail} />);
 const xs = () => [...container.querySelectorAll('[data-length-point]')].map(n => n.getAttribute('data-x'));
 expect(screen.getByRole('button', { name: 'Turns' }).getAttribute('aria-pressed')).toBe('true');
 expect(xs()).toEqual(['8', '11', '8', '11']);
 fireEvent.click(screen.getByRole('button', { name: 'Words' }));
 expect(screen.getByRole('button', { name: 'Words' }).getAttribute('aria-pressed')).toBe('true');
 expect(xs()).toEqual(['32', '44', '32', '44']);
});

it('keeps failed combos out of the plot, lists them, and keeps the table twin collapsed', () => {
 const data = base();
 const failedKey = data.combos[0].combo_key;
 const { container } = render(<ErrorVsLength data={data} legend={legendFor(data)} failed={[{ combo_key: failedKey, code: 'invalid_parameters', runs: 4, all: true }]} />);
 expect(container.querySelector(`[data-length-series="${failedKey}"]`)).toBeNull();
 expect(container.querySelectorAll('[data-length-series]')).toHaveLength(1);
 const list = screen.getByRole('list', { name: 'Not plotted' });
 expect(within(list).getByText('failed')).toBeTruthy();
 expect(screen.queryByRole('table', { name: 'Error vs length' })).toBeNull();
 fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
 expect(screen.getByRole('table', { name: 'Error vs length' })).toBeTruthy();
});

it('says so when there are no points', () => {
 const data = base(); data.error_vs_length = [];
 render(<ErrorVsLength data={data} legend={legendFor(data)} failed={noFail} />);
 expect(screen.getByText('No session length results available')).toBeTruthy();
});

it('shows the dataset session name in the data table and point tooltip', () => {
 const data = base();
 const { container } = render(<ErrorVsLength data={data} legend={legendFor(data)} failed={noFail} />);
 const titles = [...container.querySelectorAll('[data-length-point] title')].map(t => t.textContent ?? '');
 expect(titles.length).toBeGreaterThan(0);
 for (const title of titles) { expect(title).toMatch(/^syn-0[12], /); expect(title).not.toContain('synthetic-s0'); }
 fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
 const table = screen.getByRole('table', { name: 'Error vs length' });
 expect(within(table).getAllByText('syn-01').length).toBeGreaterThan(0);
 expect(table.textContent).not.toContain('synthetic-s0');
});
