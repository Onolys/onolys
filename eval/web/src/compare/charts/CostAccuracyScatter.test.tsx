// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareAnalysis } from '../compareApi';
import analysis from '../fixtures/analysis.json';
import { CostAccuracyScatter } from './CostAccuracyScatter';
import { layoutLabels } from './labelLayout';
afterEach(cleanup);
const base = () => structuredClone(analysis) as CompareAnalysis;
const legendFor = (data: CompareAnalysis) => data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
const noFail = [] as { combo_key: string; code: string; runs: number; all: boolean }[];

it('marks frontier points from the payload flags and joins only those', () => {
 const data = base();
 const { container } = render(<CostAccuracyScatter data={data} legend={legendFor(data)} failed={noFail} />);
 expect(container.querySelectorAll('[data-cost-point]')).toHaveLength(2);
 const frontier = [...container.querySelectorAll('[data-frontier="true"]')].map(n => n.getAttribute('data-cost-point'));
 expect(frontier).toEqual(data.frontier.points.map(p => p.combo_key));
 expect(container.querySelector('[data-cost-point][data-frontier="false"]')?.getAttribute('data-cost-point')).toBe(data.frontier.dominated[0].combo_key);
 expect(screen.getByRole('img', { name: 'Cost vs accuracy scatter' })).toBeTruthy();
 // Two frontier points make a line; one does not.
 data.frontier.points.push(...data.frontier.dominated); data.frontier.dominated = [];
 const two = render(<CostAccuracyScatter data={data} legend={legendFor(data)} failed={noFail} />);
 expect(two.container.querySelector('.ca-frontier')?.getAttribute('data-frontier-combos')).toBe(data.frontier.points.map(p => p.combo_key).sort((a, b) => data.frontier.points.find(p => p.combo_key === a)!.cost_per_run_usd - data.frontier.points.find(p => p.combo_key === b)!.cost_per_run_usd).join(','));
});

it('does not plot failed or unpriced combos but lists them muted, never as $0', () => {
 const data = base();
 const failedKey = data.frontier.dominated[0].combo_key;
 data.frontier.unpriced.push({ combo_key: 'unpriced', count_error: 9, n: 1, cost_per_run_usd: null, na: { reason: 'price unavailable' } });
 const { container } = render(<CostAccuracyScatter data={data} legend={legendFor(data)} failed={[{ combo_key: failedKey, code: 'invalid_parameters', runs: 4, all: true }]} />);
 expect(container.querySelectorAll('[data-cost-point]')).toHaveLength(1);
 expect(container.querySelector(`[data-cost-point="${failedKey}"]`)).toBeNull();
 expect(container.querySelector('[data-cost-point="unpriced"]')).toBeNull();
 const list = screen.getByRole('list', { name: 'Not plotted' });
 expect(within(list).getByText('failed')).toBeTruthy();
 expect(within(list).getByText(/all runs failed: invalid_parameters/)).toBeTruthy();
 expect(within(list).getByText(/unpriced.*n\/a - price unavailable/)).toBeTruthy();
 expect(list.textContent).not.toMatch(/\$0|cost 0/);
});

it('lays labels out without overlap, even for clustered points', () => {
 const pts = Array.from({ length: 7 }, (_, i) => ({ id: `c${i}`, px: 200 + (i % 2), py: 100 + i, w: 10, h: 14 }));
 const boxes = layoutLabels(pts, { left: 56, top: 12, right: 624, bottom: 308 });
 for (let i = 0; i < boxes.length; i++) {
  const a = boxes[i];
  expect(a.x).toBeGreaterThanOrEqual(56); expect(a.x + a.w).toBeLessThanOrEqual(624); expect(a.y).toBeGreaterThanOrEqual(12); expect(a.y + a.h).toBeLessThanOrEqual(308);
  for (const b of boxes.slice(i + 1)) expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h, `${a.id} overlaps ${b.id}`).toBe(false);
  for (const p of pts) expect(a.x < p.px + 8 && p.px - 8 < a.x + a.w && a.y < p.py + 8 && p.py - 8 < a.y + a.h, `${a.id} covers marker ${p.id}`).toBe(false);
 }
});

it('keeps the table twin collapsed until Show data is opened, and keeps zero values finite', () => {
 const data = base();
 data.frontier.points[0].count_error = 0; data.frontier.points[0].cost_per_run_usd = 0; data.frontier.dominated = [];
 const { container } = render(<CostAccuracyScatter data={data} legend={legendFor(data)} failed={noFail} />);
 expect(screen.queryByRole('table', { name: 'Cost vs accuracy' })).toBeNull();
 expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
 fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
 expect(screen.getByRole('table', { name: 'Cost vs accuracy' })).toBeTruthy();
});

it('says so when nothing can be plotted', () => {
 const data = base(); data.frontier.points = []; data.frontier.dominated = [];
 render(<CostAccuracyScatter data={data} legend={legendFor(data)} failed={noFail} />);
 expect(screen.getByText('No priced results available')).toBeTruthy();
});
