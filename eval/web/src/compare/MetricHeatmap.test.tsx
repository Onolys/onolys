// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareOverview } from './compareApi';
import { MetricHeatmap } from './MetricHeatmap';
import { parseCompareUrl } from './compareUrl';
import fixture from './fixtures/overview.json';
afterEach(cleanup);
const sample = () => structuredClone(fixture) as CompareOverview;
function show(data = sample()) {
 const navigate = vi.fn();
 const legend = data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
 render(<MetricHeatmap data={data} legend={legend} state={parseCompareUrl('?run=r1&view=compare')} navigate={navigate} runId="r1" />);
 return navigate;
}
const cell = (metric: string, combo = 'A') => screen.getByRole('link', { name: `${metric}, ${combo}: open Deep dive` }).closest('td')!;
const grid = () => screen.getByRole('table', { name: 'Metric heatmap' });

it('renders raw Human first, grouped rows, every n, avg miss big and signed bias small', () => {
 const data = sample(), a = data.combos[0].combo_key;
 Object.assign(data.heatmap.cells.gi[a], { off: 0.6, bias: 0.4, n: 1, within_tolerance: true, best: false });
 Object.assign(data.heatmap.cells.persuade[a], { off: 0.61, bias: -0.4, within_tolerance: false });
 Object.assign(data.heatmap.cells.cct[a], { off: 0.4, within_tolerance: true });
 Object.assign(data.heatmap.cells.sst[a], { off: 0.41, within_tolerance: false });
 show(data);
 expect(within(grid()).getAllByRole('columnheader').map(x => x.textContent)).toEqual(['Metric', 'Human', 'A', 'B']);
 expect(within(grid()).getAllByText('synthetic-s01: 1').length).toBeGreaterThan(0);
 const groups = within(grid()).getAllByRole('rowheader').filter(h => h.closest('tr')!.className.includes('overview-group')).map(h => h.textContent);
 expect(groups).toEqual(['Behavior counts', 'Globals', 'Ratios']);
 expect(cell('gi').querySelector('strong')?.textContent).toBe('0.6');
 expect(cell('gi').querySelector('small')?.textContent).toBe('+0.4');
 expect(cell('gi').textContent).toContain('n=1');
 expect(cell('persuade').textContent).toContain('-0.4');
 expect(cell('gi').className).toContain('within-tolerance'); expect(cell('persuade').className).not.toContain('within-tolerance');
 expect(cell('cct').className).toContain('within-tolerance'); expect(cell('sst').className).not.toContain('within-tolerance');
 for (const metric of ['R:Q', '%CR']) expect(cell(metric).className).not.toContain('within-tolerance');
 within(grid()).getAllByRole('cell').filter(td => td.className.includes('overview-heatmap-cell')).forEach(td => expect(td.textContent).toMatch(/n=\d/));
});
it('shows one legend row and no per-line legend paragraphs', () => {
 show();
 expect(screen.getAllByLabelText('Heatmap legend')).toHaveLength(1);
 const legend = screen.getByLabelText('Heatmap legend');
 expect(legend.tagName).toBe('UL');
 expect(legend.textContent).toMatch(/within tolerance/); expect(legend.textContent).toMatch(/best/); expect(legend.textContent).toMatch(/no tolerance/);
 expect(screen.queryByText(/How to read/)).toBeNull();
});
it('outlines best cells and suppresses best for skipped combos', () => {
 const data = sample(), key = data.combos[0].combo_key;
 show(data);
 expect(grid().querySelectorAll('.is-best').length).toBeGreaterThan(0);
 cleanup();
 Object.values(data.heatmap.cells).forEach(row => Object.assign(row[key], { value: null, off: null, bias: null, na: { reason: 'skipped: provider unavailable' }, best: true }));
 data.leaderboard[0].na = { reason: 'skipped: provider unavailable' };
 show(data);
 expect(cell('gi').textContent).toContain('skipped: provider unavailable'); expect(cell('gi').className).not.toContain('is-best');
});
it('marks a failed combo column and never outlines or tolerance-greens it', () => {
 const data = sample(), key = data.combos[0].combo_key;
 data.excluded = [1, 2, 3, 4].map(n => ({ session_id: `s${n}`, combo_key: key, reason: 'failed:invalid_parameters' }));
 Object.values(data.heatmap.cells).forEach(row => Object.assign(row[key], { best: true, within_tolerance: true }));
 show(data);
 const head = within(grid()).getByRole('columnheader', { name: /^A/ });
 expect(head.textContent).toContain('failed'); expect(head.className).toContain('is-failed');
 expect(within(head).queryByRole('link')).toBeNull();
 expect(within(grid()).getByRole('columnheader', { name: /^B/ }).querySelector('a')).toBeTruthy();
 expect(cell('gi').className).toContain('is-failed'); expect(cell('gi').className).not.toContain('is-best'); expect(cell('gi').className).not.toContain('within-tolerance');
 expect(cell('gi').textContent).not.toContain('★ best');
});
it('keeps exact missing reasons and n/a for unlabeled cells', () => {
 const data = sample(), key = data.combos[0].combo_key;
 Object.assign(data.heatmap.cells.gi[key], { value: null, off: null, bias: null, n: 0, best: false, within_tolerance: null, na: { reason: 'not labeled in this dataset' } });
 show(data);
 expect(cell('gi').querySelector('strong')?.textContent).toBe('n/a'); expect(cell('gi').textContent).toContain('not labeled in this dataset'); expect(cell('gi').textContent).toContain('n=0');
});
it('has no horizontal scroll region and drills into Deep dive with metric and combo', () => {
 const data = sample(), base = data.combos[0];
 for (let i = 2; i < 9; i++) { const combo = { ...base, combo_key: `combo-${i}` }; data.combos.push(combo); Object.values(data.heatmap.cells).forEach(row => { row[combo.combo_key] = { ...row[base.combo_key] }; }); }
 const navigate = show(data);
 expect(screen.queryByRole('region')).toBeNull(); expect(document.querySelector('[tabindex="0"]')).toBeNull();
 const link = screen.getByRole('link', { name: 'gi, A: open Deep dive' }); expect(link.getAttribute('href')).toContain('metric=gi'); fireEvent.click(link);
 expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ tab: 'deep', metric: 'gi', combos: [base.combo_key] }));
 fireEvent.click(within(grid()).getByRole('link', { name: 'A' })); expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'deep', combos: [base.combo_key] }));
});
it('hides the data table until "Show data" is pressed', () => {
 show();
 expect(screen.getAllByRole('table')).toHaveLength(1);
 const toggle = screen.getByRole('button', { name: 'Show data' });
 expect(toggle.getAttribute('aria-expanded')).toBe('false');
 fireEvent.click(toggle);
 expect(screen.getAllByRole('table')).toHaveLength(2);
 expect(screen.getByRole('table', { name: 'Metric heatmap data' })).toBeTruthy();
});
