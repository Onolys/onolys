// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { RunDetail } from '../api';
import { RunStatusChips } from './RunStatusChips';
import { UsageTiles } from './UsageTiles';
import { AlertsStrip } from './AlertsStrip';

afterEach(cleanup);
const run = (patch: Partial<RunDetail> = {}): RunDetail => ({ run_id: 'r1', name: 'Pilot', status: 'running', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['miti'], selection: null, combos: null, legacy_selection: false, combo_keys: [], combo_labels: {}, repeats: 1, total_units: 3, completed_units: 1, done_units: 1, running_units: 1, queued_units: 1, failed_units: 0, cancelled_units: 0, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: 0, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, units: [], ...patch });
const chip = (text: string) => screen.getByText(text).closest('.ui-chip')!;

it('shows one chip per state with tone and icon; zero counts are muted', () => {
  render(<RunStatusChips run={run()} />);
  const group = screen.getByRole('status', { name: 'Run status' });
  expect(group.textContent).toBe('Running1 of 3 done1 running1 queued0 failed0 cancelled');
  expect(chip('Running').className).toContain('ui-chip-info');
  expect(chip('1 of 3 done').className).toContain('ui-chip-success');
  expect(chip('1 running').className).toContain('ui-chip-info');
  expect(chip('1 queued').className).toContain('ui-chip-neutral');
  expect(chip('0 failed').className).toContain('ui-chip-muted');
  expect(chip('0 cancelled').className).toContain('ui-chip-muted');
  for (const c of group.querySelectorAll('.ui-chip')) expect(c.querySelector('svg')).toBeTruthy();
});
it('non-zero failed is danger, non-zero cancelled is not muted', () => {
  render(<RunStatusChips run={run({ failed_units: 2, cancelled_units: 1 })} />);
  expect(chip('2 failed').className).toContain('ui-chip-danger');
  expect(chip('1 cancelled').className).not.toContain('ui-chip-muted');
});
it('zero done is muted', () => {
  render(<RunStatusChips run={run({ done_units: 0 })} />);
  expect(chip('0 of 3 done').className).toContain('ui-chip-muted');
});
it.each([['queued', 'Queued', 'neutral'], ['running', 'Running', 'info'], ['done', 'Done', 'success'], ['partial', 'Partial', 'warning'], ['failed', 'Failed', 'danger'], ['cancelled', 'Cancelled', 'muted']] as const)('overall %s chip is %s / %s', (status, label, tone) => {
  render(<RunStatusChips run={run({ status })} />);
  expect(chip(label).className).toContain(`ui-chip-${tone}`);
});
it('running/queued chips only appear while the run is active', () => {
  render(<RunStatusChips run={run({ status: 'done' })} />);
  expect(screen.queryByText(/running$/)).toBeNull(); expect(screen.queryByText(/queued$/)).toBeNull();
});
it('cancel requested shows a Cancelling chip', () => {
  render(<RunStatusChips run={run({ cancel_requested: true })} />);
  expect(chip('Cancelling').className).toContain('ui-chip-warning'); expect(screen.queryByText('Running')).toBeNull();
});
it('progress bar value is finished units over total', () => {
  render(<RunStatusChips run={run({ completed_units: 1 })} />);
  const bar = screen.getByRole('progressbar', { name: 'Run progress' });
  expect(bar.getAttribute('aria-valuenow')).toBe('33'); expect(bar.getAttribute('aria-valuemin')).toBe('0'); expect(bar.getAttribute('aria-valuemax')).toBe('100');
  cleanup(); render(<RunStatusChips run={run({ total_units: 0, completed_units: 0 })} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0');
});

it('usage tiles show tokens, cost, started and the muted STT note', () => {
  render(<UsageTiles run={run({ usage: { input_tokens: 12345, output_tokens: 4 }, cost_usd_est: 0.0123 })} now={Date.parse('2026-11-23T10:05:12Z')} />);
  expect(screen.getByText('Input tokens').nextElementSibling!.textContent).toBe('12,345');
  expect(screen.getByText('Output tokens').nextElementSibling!.textContent).toBe('4');
  expect(screen.getByText('Est. cost').nextElementSibling!.textContent).toBe('~$0.0123');
  expect(screen.getByText('Started')).toBeTruthy(); expect(screen.getByText(/Elapsed 5m 12s/)).toBeTruthy();
  const note = screen.getByText('Cost is an estimate. Speech-to-text is not included.');
  expect(note.className).toContain('ui-note');
});
it('cost shows an em dash when unknown; zero tokens are muted', () => {
  render(<UsageTiles run={run({ cost_usd_est: null })} />);
  expect(screen.getByText('Est. cost').nextElementSibling!.textContent).toBe('—');
  expect(screen.getByText('Input tokens').nextElementSibling!.className).toContain('ui-zero');
});
it('unpriced units are explained in a popover behind the cost tile', () => {
  render(<UsageTiles run={run({ unpriced_units: 2 })} />);
  expect(screen.queryByText(/estimate is incomplete/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '2 unpriced' }));
  expect(screen.getByText(/2 units have no price data/)).toBeTruthy();
});
it('elapsed stops at cancelled_at and is hidden for finished runs without an end time', () => {
  render(<UsageTiles run={run({ status: 'partial', cancelled_at: '2026-11-23T10:02:00Z' })} now={Date.parse('2026-11-23T11:00:00Z')} />);
  expect(screen.getByText(/Elapsed 2m 0s/)).toBeTruthy(); cleanup();
  render(<UsageTiles run={run({ status: 'done' })} now={Date.parse('2026-11-23T11:00:00Z')} />);
  expect(screen.queryByText(/Elapsed/)).toBeNull();
});

it('alerts strip is hidden on a clean run', () => {
  const view = render(<AlertsStrip run={run({ status: 'done' })} />);
  expect(view.container.innerHTML).toBe('');
});
it('alerts strip merges skips, busy, cancel requested, partial and run error', () => {
  render(<AlertsStrip run={run({ status: 'partial', cancelled_at: '2026-11-23T10:02:00Z', skipped_units: 1, cancel_requested: false, provider_skips: [{ provider: 'gemini', after_failures: 5, skipped_cells: 2, skipped_at: 't' }], provider_cooldowns: [{ provider: 'openai', cooldown_until: 't' }] })} />);
  expect(screen.getByText(/Gemini skipped after 5 failures/)).toBeTruthy();
  expect(screen.getByText('OpenAI is busy — waiting to retry')).toBeTruthy();
  expect(document.querySelector('[data-partial-badge]')?.textContent).toContain('Partial —');
  cleanup();
  render(<AlertsStrip run={run({ cancel_requested: true })} />);
  expect(screen.getByText('Cancelled — runs already in progress will finish; no new runs start.')).toBeTruthy(); cleanup();
  render(<AlertsStrip run={run({ status: 'failed', error: { code: 'enqueue_failed' } })} />);
  expect(screen.getByRole('alert').textContent).toContain('Run failed to start');
});
