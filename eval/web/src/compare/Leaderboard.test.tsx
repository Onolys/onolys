// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareOverview } from './compareApi';
import { Leaderboard } from './Leaderboard';
import { parseCompareUrl } from './compareUrl';
import fixture from './fixtures/overview.json';
afterEach(cleanup);
const sample = () => structuredClone(fixture) as CompareOverview;
function show(data = sample()) {
 const navigate = vi.fn();
 const legend = data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
 render(<Leaderboard data={data} legend={legend} state={parseCompareUrl('?run=r1&view=compare')} navigate={navigate} runId="r1" />);
 return navigate;
}
const table = () => screen.getByRole('table');
const order = () => within(table()).getAllByRole('row').slice(1).map(r => r.querySelector('td')!.textContent!.slice(0, 1));
const header = (name: string) => within(table()).getByRole('columnheader', { name });
const failFirst = (data: CompareOverview) => {
 const key = data.combos[0].combo_key;
 data.excluded = [1, 2, 3, 4].map(n => ({ session_id: `s${n}`, combo_key: key, reason: 'failed:invalid_parameters' }));
 data.header.sessions = 2; data.header.repeats = 2;
 return key;
};

it('header cells are plain th with sort arrows, never buttons', () => {
 show();
 expect(within(table()).queryAllByRole('button')).toHaveLength(0);
 for (const name of ['Combo', 'Count error', 'Globals within ±1', 'Line match accuracy', 'Line match macro F1', 'Fails', 'Cost', 'Time']) expect(header(name).tagName).toBe('TH');
 expect(header('Cost').querySelector('svg')).toBeTruthy();
});
it('sorts every column ascending then descending from the saved values', () => {
 const data = sample(), [a, b] = data.leaderboard;
 a.off = 1; b.off = 2; a.globals_within_1.value = 0.7; b.globals_within_1.value = 0.9;
 a.line_accuracy = { ...a.line_accuracy, value: 0.6 }; b.line_accuracy = { ...b.line_accuracy, value: 0.8, na: null };
 a.macro_f1 = { ...a.macro_f1, value: 0.9 }; b.macro_f1 = { ...b.macro_f1, value: 0.7, na: null };
 a.failures = [{ code: 'provider_error', count: 3 }]; b.failures = [];
 a.cost.per_run_usd = 0.1; b.cost.per_run_usd = 0.2; a.time.mean_seconds = 12; b.time.mean_seconds = 8;
 show(data);
 for (const [name, asc] of [['Count error', 'A'], ['Globals within ±1', 'A'], ['Line match accuracy', 'A'], ['Line match macro F1', 'B'], ['Fails', 'B'], ['Cost', 'A'], ['Time', 'B']]) {
  fireEvent.click(header(name));
  expect(order()[0], `${name} asc`).toBe(asc);
  expect(header(name).getAttribute('aria-sort')).toBe('ascending');
  fireEvent.click(header(name));
  expect(order()[0], `${name} desc`).toBe(asc === 'A' ? 'B' : 'A');
  expect(header(name).getAttribute('aria-sort')).toBe('descending');
 }
});
it('marks best with star + "best" from server flags only, per metric', () => {
 const data = sample();
 data.leaderboard.forEach(r => { r.operational_best = { failures: false, cost: false, time: false }; });
 data.leaderboard[0].operational_best.cost = true;
 show(data);
 expect(within(table()).getAllByText('★ best').length).toBeGreaterThan(1);
 const rows = within(table()).getAllByRole('row').slice(1);
 const costBest = rows.filter(r => r.querySelector('[data-label="Cost"]')!.textContent!.includes('★ best'));
 expect(costBest).toHaveLength(1);
 rows.forEach(r => { expect(r.querySelector('[data-label="Time"]')!.textContent).not.toContain('best'); });
});
it('shades a failed combo row red, shows a failed chip with code, and never stars it', () => {
 const data = sample(), key = failFirst(data);
 data.leaderboard.forEach(r => { r.operational_best = { failures: true, cost: true, time: true }; r.globals_within_1.best = true; r.best = true; });
 show(data);
 const row = within(table()).getAllByRole('row').slice(1).find(r => r.textContent!.includes(key))!;
 expect(row.className).toContain('ui-row-danger');
 expect(within(row).getByText('failed').closest('[title]')!.getAttribute('title')).toBe('failed: invalid_parameters');
 expect(within(row).getByText('all failed').closest('[title]')!.getAttribute('title')).toBe('invalid_parameters');
 expect(row.querySelector('[data-label="Cost"]')!.textContent).toBe('—');
 expect(row.querySelector('[data-label="Time"]')!.textContent).toBe('—');
 expect(row.querySelector('[data-bar]')).toBeNull();
 expect(row.textContent).not.toContain('per run');
 expect(within(row).queryByText('★ best')).toBeNull();
 const other = within(table()).getAllByRole('row').slice(1).find(r => !r.textContent!.includes(key))!;
 expect(other.className).not.toContain('ui-row-danger');
 expect(within(other).getAllByText('★ best').length).toBeGreaterThan(0);
});
it('formats cost and time readably and draws inline mini bars', () => {
 const data = sample();
 data.leaderboard[0].cost.per_run_usd = 0.1367285; data.leaderboard[0].time.mean_seconds = 66.639094;
 show(data);
 expect(screen.getByText('$0.137')).toBeTruthy();
 expect(screen.getByText('66.6 s')).toBeTruthy();
 expect(table().textContent).not.toContain('0.1367285');
 expect(table().querySelectorAll('[data-bar="cost"]').length).toBe(data.leaderboard.length);
 expect(table().querySelectorAll('[data-bar="time"]').length).toBe(data.leaderboard.length);
});
it('hides quality columns without a human reference', () => {
 const data = sample(); data.has_human = false; show(data);
 expect(within(table()).queryByRole('columnheader', { name: 'Count error' })).toBeNull();
 for (const name of ['Fails', 'Cost', 'Time']) expect(header(name)).toBeTruthy();
});
it('suppresses best for skipped rows and shows exact missing reasons', () => {
 const data = sample(); data.leaderboard[0].na = { reason: 'skipped: provider unavailable' };
 data.leaderboard.forEach(r => { r.operational_best = { failures: true, cost: true, time: true }; });
 show(data);
 const skipped = within(table()).getAllByRole('row').find(r => r.textContent!.includes('skipped'))!;
 expect(within(skipped).queryByText('★ best')).toBeNull();
});
it('excludes all-failed combos from bar scaling and keeps partial failures as one chip-line per code', () => {
 const data = sample(), key = failFirst(data);
 data.leaderboard[0].cost.per_run_usd = 100; data.leaderboard[0].time.mean_seconds = 900;
 data.leaderboard[1].cost.per_run_usd = 0.2; data.leaderboard[1].time.mean_seconds = 10;
 data.leaderboard[1].failures = [{ code: 'invalid_parameters', count: 2 }, { code: 'timeout', count: 1 }];
 show(data);
 const other = within(table()).getAllByRole('row').slice(1).find(r => !r.textContent!.includes(key))!;
 expect((other.querySelector('[data-bar="cost"] i') as HTMLElement).style.width).toBe('100%');
 expect(within(other).getByText('2 × invalid_parameters').className).toContain('lb-code');
 expect(within(other).getByText('1 × timeout')).toBeTruthy();
});
it('orders two n/a rows without NaN (stable)', () => {
 const data = sample(); data.leaderboard.forEach(r => { r.na = { reason: 'x' } as never; });
 show(data);
 expect(within(table()).getAllByRole('row').length).toBe(data.leaderboard.length + 1);
});
