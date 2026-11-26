// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareOverview } from './compareApi';
import { ComparisonHeader } from './ComparisonHeader';
import overviewFixture from './fixtures/overview.json';
afterEach(cleanup);
const base = overviewFixture as unknown as CompareOverview;
const legend = base.combos.map((combo, index) => ({ combo, letter: String.fromCharCode(65 + index), label: combo.combo_key }));
const show = (data: CompareOverview, extra: Record<string, unknown> = {}) => render(<ComparisonHeader data={data} runId="r1" navigate={vi.fn()} legend={legend} {...extra}/>);
const incomplete = (n: number) => ({
 ...base, cohorts: Object.fromEntries(Object.keys(base.cohorts).map((k, i) => [k, { paired: i < n ? 0 : 2, of: 2 }])),
}) as CompareOverview;

it('titles the page exactly "Compare - <name>" with a Back to run link and no jumbled text', () => {
 show(base);
 expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Compare - Synthetic lines');
 expect(screen.getByRole('link', { name: 'Back to run' }).getAttribute('href')).toBe('?run=r1');
 expect(screen.queryByText(/^Human labels:/)).toBeNull();
 expect(screen.queryByText(/^gi: paired/)).toBeNull();
 expect(screen.queryByText(/^Coverage:/)).toBeNull();
});
it('falls back to the run id when the run has no name', () => {
 show({ ...base, header: { ...base.header, name: null } });
 expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Compare - r1');
});
it('renders four summary cards from the payload', () => {
 show(base);
 const sessions = screen.getByText('Sessions').closest('.ui-summary') as HTMLElement;
 expect(within(sessions).getByText('2')).toBeTruthy();
 expect(within(sessions).getByText('2 attempts each · 2 combos')).toBeTruthy();
 const labels = screen.getByText('Human labels').closest('.ui-summary') as HTMLElement;
 expect(within(labels).getByText('All 10 counts')).toBeTruthy();
 expect(within(labels).getByText('4 globals')).toBeTruthy();
 const coverage = screen.getByText('Coverage').closest('.ui-summary') as HTMLElement;
 expect(within(coverage).getByText('8 of 8 runs done, 0 skipped')).toBeTruthy();
 expect(within(coverage).getByText('20 of 20 complete').className).toContain('ui-chip-success');
 const excluded = screen.getByText('Excluded').closest('.ui-summary') as HTMLElement;
 expect(within(excluded).getByText('0')).toBeTruthy();
 expect(within(excluded).getByText('Nothing excluded')).toBeTruthy();
});
it('shows labels as unavailable and no partial badge for a finished run', () => {
 const { container } = show({ ...base, header: { ...base.header, label_coverage: null } });
 expect(screen.getByText('No human labels')).toBeTruthy();
 expect(container.querySelector('[data-partial-badge]')).toBeNull();
});
it('shows the partial badge and skipped-provider notice', () => {
 const partial = { ...base, header: { ...base.header, progress: { done_units: 11, total_units: 15, skipped_units: 2 } }, coverage: { ...base.coverage, eval_status: 'partial', runs_done: 3, runs_total: 8, runs_skipped: 2, skipped_providers: [{ provider: 'gemini', after_failures: 5 }] } } as CompareOverview;
 const { container } = show(partial);
 expect(container.querySelector('[data-partial-badge]')!.textContent).toContain('Partial — 11 of 15 runs done, 2 skipped');
 expect(screen.getByText(/Gemini skipped after 5 failures in a row/)).toBeTruthy();
 expect(screen.getByText('3 of 8 runs done, 2 skipped')).toBeTruthy();
});
it('marks incomplete coverage amber, listing at most three and hiding the rest behind Show all', () => {
 show(incomplete(5));
 const coverage = screen.getByText('Coverage').closest('.ui-summary') as HTMLElement;
 const amber = within(coverage).getAllByText(/paired 0 of 2/);
 expect(amber).toHaveLength(3);
 amber.forEach(chip => expect(chip.className).toContain('ui-chip-warning'));
 expect(within(coverage).getByText('15 of 20 complete').className).toContain('ui-chip-warning');
 fireEvent.click(within(coverage).getByRole('button', { name: 'Show all' }));
 expect(within(coverage).getAllByText(/paired 0 of 2/)).toHaveLength(5);
 expect(within(coverage).getAllByText(/paired 2 of 2/)).toHaveLength(15);
});
it('has no Show all toggle when all coverage fits', () => {
 show(base);
 expect(screen.queryByRole('button', { name: 'Show all' })).toBeNull();
});
it('Excluded card lists the failed combo with its error code', () => {
 const [first] = base.combos;
 const failed = { ...base, excluded: [0, 1].flatMap(repeat => ['s1', 's2'].map(session_id => ({ session_id, combo_key: first.combo_key, repeat, reason: 'failed:invalid_parameters' }))) } as CompareOverview;
 show(failed);
 const card = screen.getByText('Excluded').closest('.ui-summary') as HTMLElement;
 expect(within(card).getByText('1')).toBeTruthy();
 expect(within(card).getByText('A: invalid_parameters').className).toContain('ui-chip-danger');
 expect(within(card).getByText('all runs failed')).toBeTruthy();
});
it('Excluded card lists non-combo exclusions by reason', () => {
 show({ ...base, excluded: [{ session_id: 's1', combo_key: null, reason: 'cancelled' }] } as CompareOverview);
 const card = screen.getByText('Excluded').closest('.ui-summary') as HTMLElement;
 expect(within(card).getByText('s1: cancelled')).toBeTruthy();
});
it('Config opens the saved-configuration popup only when the run detail is loaded', () => {
 show(base);
 expect(screen.queryByRole('button', { name: 'Config' })).toBeNull();
 cleanup();
 const run = { run_id: 'r1', name: 'Synthetic lines', engines: ['miti'], combo_keys: [], input: {}, repeats: 2 };
 show(base, { run });
 fireEvent.click(screen.getByRole('button', { name: 'Config' }));
 expect(screen.getByRole('dialog')).toBeTruthy();
 expect(screen.getByText('Run configuration')).toBeTruthy();
});
it('styles Back to run as an arrow back link and has no coverage prop', () => {
 show(base);
 const link = screen.getByRole('link', { name: 'Back to run' });
 expect(link.className).toContain('compare-back');
 expect(link.textContent).toContain('←');
});
