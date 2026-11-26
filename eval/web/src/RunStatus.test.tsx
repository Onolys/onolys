// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { History, RunView } from './Runs';
import { PartialBadge, ProviderSkipNotices } from './RunStatus';
import { createEvalApi, type RunDetail } from './api';
afterEach(cleanup);
const saved = (patch: Partial<RunDetail> = {}): RunDetail => ({ run_id: 'r1', name: 'Morning', status: 'partial', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['miti'], selection: null, combos: null, legacy_selection: true, combo_keys: [], combo_labels: {}, repeats: 1, total_units: 9, completed_units: 8, done_units: 3, failed_units: 2, cancelled_units: 3, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: null, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, units: [], ...patch });
it.each(['detail', 'history'])('%s shows each partial/cancelled variant with API done counters', async page => {
 for (const [patch, expected] of [
  [{ cancelled_at: '2026-11-23T12:34:00Z', skipped_units: 2 }, `Partial — cancelled at ${new Date('2026-11-23T12:34:00Z').toLocaleString()}, 3 of 9 runs done, 2 skipped`],
  [{}, 'Partial — 3 of 9 runs done'],
  [{ status: 'cancelled', done_units: 0 }, 'Cancelled — no runs completed'],
 ] as const) {
  const run = saved(patch); const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run), runs: vi.fn().mockResolvedValue({ runs: [run] }) };
  const view = render(page === 'detail' ? <RunView api={api} runId="r1" onRerun={vi.fn()} /> : <History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await act(async () => {});
  expect(screen.getAllByText(page === 'history' ? expected.replace(/^Partial — /, '') : expected, { exact: false }).length).toBeGreaterThan(0); expect(document.body.textContent).not.toContain('8 of 9 runs done');
  if (run.status === 'partial') expect(document.querySelector('[data-partial-badge]')?.textContent).toContain('◐'); view.unmount();
 }
});
it('exports a reusable partial badge, preserves invalid saved timestamps and omits it for complete runs', () => {
 const view = render(<PartialBadge run={saved({ cancelled_at: 'saved-time', skipped_units: 0 })} />);
 expect(screen.getByText('Partial — cancelled at saved-time, 3 of 9 runs done', { exact: false })).toBeTruthy();
 view.rerender(<PartialBadge run={saved({ status: 'done' })} />); expect(document.querySelector('[data-partial-badge]')).toBeNull();
});
it('short partial badge is a compact pill with the detail outside it', () => {
 render(<PartialBadge short run={saved({ cancelled_at: 'saved-time', skipped_units: 1 })} />);
 const badge = document.querySelector('[data-partial-badge]')!;
 expect(badge.textContent).toBe('◐ Partial'); expect(badge.className).not.toContain('whitespace-normal');
 expect(document.querySelector('[data-partial-detail]')?.textContent).toBe('cancelled at saved-time, 3 of 9 runs done, 1 skipped');
});
it.each(['detail', 'history'])('%s shows provider skips with a symbol, mapped name and unknown-id fallback', async page => {
 const run = saved({ provider_skips: [{ provider: 'gemini', after_failures: 5, skipped_cells: 2, skipped_at: 'saved-time' }, { provider: 'new-provider', after_failures: 7, skipped_cells: 1, skipped_at: 'saved-time' }] });
 const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run), runs: vi.fn().mockResolvedValue({ runs: [run] }) };
 render(page === 'detail' ? <RunView api={api} runId="r1" onRerun={vi.fn()} /> : <History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await act(async () => {});
 const suffix = page === 'detail' ? ' in a row — provider may be down' : '';
 expect(screen.getByText(`Gemini skipped after 5 failures${suffix}`, { exact: false })).toBeTruthy(); expect(screen.getByText(`new-provider skipped after 7 failures${suffix}`, { exact: false })).toBeTruthy();
 expect(document.querySelector('[data-provider-skips]')?.textContent).toContain('⚠');
});
it('accepts Compare provider skips without run-only fields', () => {
 render(<ProviderSkipNotices skips={[{ provider: 'gemini', after_failures: 5 }]} />); expect(screen.getByText('Gemini skipped after 5 failures in a row — provider may be down', { exact: false })).toBeTruthy();
});
it('renders skipped units as skipped and n/a with the API reason; shows provider cooldown copy', async () => {
 const run = saved({ provider_cooldowns: [{ provider: 'gemini', cooldown_until: '2026-11-23T12:34:00Z' }], units: [{ unit_id: 'u1', session_id: 's1', engine: 'miti', status: 'skipped', error: { code: 'provider_unavailable', message: 'skipped: provider unavailable' } }, { unit_id: 'u2', session_id: 's1', engine: 'miti', status: 'waiting' }] });
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />); await act(async () => {});
 const row = screen.getByRole('cell', { name: 'skipped' }).closest('tr')!;
 expect(within(row).getByRole('cell', { name: /n\/a.*skipped: provider unavailable/ })).toBeTruthy();
 expect(screen.getByText('Gemini is busy — waiting to retry')).toBeTruthy(); expect(screen.getByRole('cell', { name: 'waiting' })).toBeTruthy();
 expect(screen.getAllByText(/3\/9 runs done/)).toHaveLength(2); expect(screen.queryByText(/8\/9 units complete/)).toBeNull();
});
it('shows running units with their stage, queued units without one, and live run progress', async () => {
 const run = saved({ status: 'running', total_units: 3, done_units: 1, running_units: 1, queued_units: 1, units: [
  { unit_id: 'u1', session_id: 's1', engine: 'miti', status: 'done' },
  { unit_id: 'u2', session_id: 's1', engine: 'miti', status: 'running', stage: 'coding' },
  { unit_id: 'u3', session_id: 's2', engine: 'miti', status: 'queued' }] });
 const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run), runs: vi.fn().mockResolvedValue({ runs: [run] }) };
 const detail = render(<RunView api={api} runId="r1" onRerun={vi.fn()} />); await act(async () => {});
 expect(screen.getByText(/1\/3 runs done · 1 running · 1 queued/)).toBeTruthy();
 const running = screen.getByRole('cell', { name: 'running' }).closest('tr')!; expect(within(running).getByRole('cell', { name: 'coding' })).toBeTruthy();
 const queued = screen.getByRole('cell', { name: 'queued' }).closest('tr')!; expect(within(queued).queryByText('coding')).toBeNull();
 detail.unmount(); render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await act(async () => {});
 expect(screen.getByText('1 of 3 runs done, 1 running')).toBeTruthy();
});
it('shows a readable reason for a run that failed before starting (enqueue_failed)', async () => {
 const run = saved({ status: 'failed', done_units: 0, failed_units: 0, cancelled_units: 0, error: { code: 'enqueue_failed' } });
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />); await act(async () => {});
 expect(screen.getByRole('alert').textContent).toContain('Run failed to start: could not queue it for processing');
 expect(screen.getAllByRole('status').some(el => el.textContent?.includes('failed'))).toBe(true);
});
