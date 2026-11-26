// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { CompareAnalysis } from '../compareApi';
import analysis from '../fixtures/analysis.json';
import { BaselineCard } from './BaselineCard';
import { ReliabilityTable } from './ReliabilityTable';
afterEach(cleanup);
const base = () => structuredClone(analysis) as CompareAnalysis;
const legendFor = (data: CompareAnalysis) => data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
const order = () => screen.getAllByRole('row').slice(1).map(r => within(r).getAllByRole('img')[0].getAttribute('aria-label'));

it('shows repeat agreement, fails and time per combo and sorts by header', () => {
 const data = base(), [a, b] = data.combos.map(c => c.combo_key);
 data.reliability[a].failures = [{ code: 'provider_unavailable', count: 3 }];
 data.reliability[b].failures = [];
 render(<ReliabilityTable data={data} legend={legendFor(data)} failed={[]} />);
 const table = screen.getByRole('table', { name: 'Reliability' });
 expect(within(table).getByText(/lines 56%/)).toBeTruthy();
 expect(within(table).getByText(/5 of 9 agree/)).toBeTruthy();
 expect(within(table).getByText(/3 × provider_unavailable/)).toBeTruthy();
 expect(within(table).getAllByText(/75 s/)).toHaveLength(2);
 expect(order()).toEqual(['Combo A', 'Combo B']);
 const fails = within(table).getByRole('columnheader', { name: /Fails/ });
 fireEvent.click(fails);
 expect(fails.getAttribute('aria-sort')).toBe('ascending');
 expect(order()).toEqual(['Combo B', 'Combo A']);
 fireEvent.click(fails);
 expect(fails.getAttribute('aria-sort')).toBe('descending');
 expect(order()).toEqual(['Combo A', 'Combo B']);
});

it('shades an all-failed combo red with a text chip and no cost-free numbers', () => {
 const data = base(), b = data.combos[1].combo_key;
 render(<ReliabilityTable data={data} legend={legendFor(data)} failed={[{ combo_key: b, code: 'invalid_parameters', runs: 4, all: true }]} />);
 const rows = screen.getAllByRole('row').slice(1);
 expect(rows[0].className).not.toMatch(/ui-row-danger/);
 expect(rows[1].className).toMatch(/ui-row-danger/);
 expect(within(rows[1]).getByText('all runs failed')).toBeTruthy();
 expect(within(rows[1]).queryByText(/ s$/)).toBeNull();
});

it('never marks a failed combo best, even when the server flag is set', () => {
 const data = base(), [a, b] = data.combos.map(c => c.combo_key);
 render(<ReliabilityTable data={data} legend={legendFor(data)} failed={[{ combo_key: b, code: 'x', runs: 4, all: true }]}
  best={{ [a]: { failures: true, time: true }, [b]: { failures: true, time: true } }} />);
 const rows = screen.getAllByRole('row').slice(1);
 expect(within(rows[0]).getAllByText('★ best').length).toBeGreaterThan(0);
 expect(within(rows[1]).queryByText('★ best')).toBeNull();
});

it('prints the baseline as n/a text with the server reason', () => {
 render(<BaselineCard baseline={base().baseline} />);
 expect(screen.getByText('Human-vs-human baseline')).toBeTruthy();
 expect(screen.getByText('n/a')).toBeTruthy();
 expect(screen.getByText(/Needs a second human coder, not in this dataset/)).toBeTruthy();
});
