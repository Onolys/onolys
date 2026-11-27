// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { RunDetail } from '../api';
import { RunHeader } from './RunHeader';
import { buildCompareUrl } from '../compare/compareUrl';
import { runLogsUrl } from './logsUrl';

afterEach(cleanup);
const run = (patch: Partial<RunDetail> = {}): RunDetail => ({ run_id: 'run_7f3a91c2e8b4', name: 'Pilot 4', description: 'Two engines on AnnoMI', status: 'running', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['miti'], selection: null, combos: null, legacy_selection: false, combo_keys: [], combo_labels: {}, repeats: 1, total_units: 2, completed_units: 0, done_units: 0, failed_units: 0, cancelled_units: 0, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: 0, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, units: [{ unit_id: 'abc123', session_id: 's1', engine: 'miti', status: 'running' }, { unit_id: 'def456', session_id: 's1', engine: 'miti', status: 'queued' }], ...patch });
const setup = (r: RunDetail, handlers: Partial<Parameters<typeof RunHeader>[0]> = {}) => render(<RunHeader run={r} onConfig={vi.fn()} onRerun={vi.fn()} onCancel={vi.fn()} onNavigate={vi.fn()} {...handlers} />);

it('title is exactly "Run - <name>" with a muted description', () => {
  setup(run());
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Run - Pilot 4');
  expect(screen.getByText('Two engines on AnnoMI')).toBeTruthy();
});
it('falls back to the run id when unnamed', () => {
  setup(run({ name: null, description: null }));
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Run - run_7f3a91c2e8b4');
});
it('shows the run id and copies it', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  setup(run());
  expect(screen.getByText('run_7f3a91c2e8b4').tagName).toBe('CODE');
  fireEvent.click(screen.getByRole('button', { name: 'Copy run id' }));
  expect(writeText).toHaveBeenCalledWith('run_7f3a91c2e8b4');
});
it('no id appears in any button label', () => {
  setup(run());
  for (const button of screen.getAllByRole('button')) expect(button.textContent).not.toMatch(/run_7f3a91c2e8b4|abc123/);
});
it('Logs link uses the run-level logs URL from the unit ids', () => {
  setup(run());
  const link = screen.getByRole('link', { name: 'Logs' });
  expect(link.getAttribute('href')).toBe(runLogsUrl(['abc123', 'def456'])!.url);
  expect(link.getAttribute('target')).toBe('_blank');
  expect(link.getAttribute('rel')).toContain('noopener');
});
it('Logs is disabled with a hint when no unit has a worker run id', () => {
  setup(run({ units: [{ unit_id: 'cell-1', session_id: 's1', engine: 'miti', status: 'queued' }] }));
  expect(screen.queryByRole('link', { name: 'Logs' })).toBeNull();
  const logs = screen.getByText('Logs').closest('[aria-disabled]')!;
  expect(logs.getAttribute('aria-disabled')).toBe('true');
  expect(logs.getAttribute('title')).toMatch(/no logs yet/i);
});
it('Config / Rerun… / Cancel buttons call back; Compare is a link when results exist', () => {
  const onConfig = vi.fn(), onRerun = vi.fn(), onCancel = vi.fn(), onNavigate = vi.fn();
  const r = run();
  const view = setup(r, { onConfig, onRerun, onCancel, onNavigate });
  fireEvent.click(screen.getByRole('button', { name: 'Config' })); expect(onConfig).toHaveBeenCalledWith(r, expect.any(HTMLElement));
  fireEvent.click(screen.getByRole('button', { name: 'Rerun…' })); expect(onRerun).toHaveBeenCalledWith(r);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' })); expect(onCancel).toHaveBeenCalledWith(r, expect.any(HTMLElement));
  expect(screen.queryByRole('link', { name: 'Compare' })).toBeNull();
  const off = screen.getByRole('button', { name: 'Compare' }) as HTMLButtonElement;
  expect(off.disabled).toBe(true); expect(off.getAttribute('title')).toBe('Compare opens when the run has finished results');
  expect(document.getElementById(off.getAttribute('aria-describedby') ?? '')?.textContent).toBe('Compare opens when the run has finished results');
  view.unmount();
  setup(run({ status: 'done' }), { onNavigate });
  fireEvent.click(screen.getByRole('link', { name: 'Compare' })); expect(onNavigate).toHaveBeenCalled();
});
it.each(['queued', 'running'] as const)('Cancel shown for %s; hidden once cancel requested', status => {
  setup(run({ status })); expect(screen.getByRole('button', { name: 'Cancel run' })).toBeTruthy();
  cleanup(); setup(run({ status, cancel_requested: true })); expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull();
});
it.each(['done', 'partial', 'failed', 'cancelled'] as const)('Cancel hidden for %s', status => {
  setup(run({ status })); expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull();
  expect(within(screen.getByRole('region', { name: 'Run summary' })).getByRole('button', { name: 'Config' })).toBeTruthy();
});
it('done: green Compare link-button right beside Rerun, href is the compare overview', () => {
  const onNavigate = vi.fn();
  setup(run({ status: 'done' }), { onNavigate });
  const compare = screen.getByRole('link', { name: 'Compare' });
  expect(compare.getAttribute('href')).toBe(buildCompareUrl({ run: 'run_7f3a91c2e8b4', view: 'compare', tab: 'overview' }, window.location.search));
  expect(compare.getAttribute('href')).toContain('view=compare');
  expect(compare.className).toContain('run-compare-go');
  expect(compare.className).toContain('run-compact');
  expect(compare.nextElementSibling).toBe(screen.getByRole('button', { name: 'Rerun…' }));
  fireEvent.click(compare);
  expect(onNavigate).toHaveBeenCalledWith({ run: 'run_7f3a91c2e8b4', view: 'compare', tab: 'overview' });
});
it('done: modified click is left to the browser (new tab still works)', () => {
  const onNavigate = vi.fn();
  setup(run({ status: 'done' }), { onNavigate });
  fireEvent.click(screen.getByRole('link', { name: 'Compare' }), { ctrlKey: true });
  expect(onNavigate).not.toHaveBeenCalled();
});
it('partial: Compare stays an enabled link but is not green', () => {
  const onNavigate = vi.fn();
  setup(run({ status: 'partial' }), { onNavigate });
  const compare = screen.getByRole('link', { name: 'Compare' });
  expect(compare.className).not.toContain('run-compare-go');
  fireEvent.click(compare); expect(onNavigate).toHaveBeenCalled();
});
it.each(['queued', 'running', 'failed', 'cancelled'] as const)('%s: Compare is the disabled grey button', status => {
  setup(run({ status }));
  expect(screen.queryByRole('link', { name: 'Compare' })).toBeNull();
  const off = screen.getByRole('button', { name: 'Compare' }) as HTMLButtonElement;
  expect(off.disabled).toBe(true); expect(off.className).not.toContain('run-compare-go');
});
