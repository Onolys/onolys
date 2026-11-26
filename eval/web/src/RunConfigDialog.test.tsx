// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { RunSummary } from './api';
import { RunConfigDialog } from './RunConfigDialog';

afterEach(cleanup);
const run = (over: Partial<RunSummary> = {}): RunSummary => ({
  run_id: 'run_7f3a', status: 'done', created_at: '2026-11-26T09:00:00Z', name: 'Pilot 4',
  input: { dataset_id: 'annomi-sample', session_ids: ['gi', 'persuade'] }, engines: ['miti', 'oneshot:miti', 'human'],
  selection: null, combos: [{ model: 'claude-sonnet-4.5', tier: 'standard', effort: 'medium' }, { model: 'gpt-5', tier: 'standard', effort: 'high' }],
  legacy_selection: false, combo_keys: ['a', 'b'], combo_labels: {}, repeats: 3, change_goal: 'reduce alcohol use', language: 'en',
  total_units: 4, completed_units: 4, done_units: 4, failed_units: 0, cancelled_units: 0, usage: { input_tokens: 1, output_tokens: 1 }, cost_usd_est: null, unpriced_units: 0,
  engine_versions: { miti: '4.2.1', 'oneshot:miti': '0.3.0' }, engine_git_sha: { miti: 'abc123' }, resolved_presets: {}, ...over,
});
const open = (r: RunSummary | null = run(), onClose = vi.fn()) => render(<RunConfigDialog run={r} onClose={onClose} returnFocus={createRef()} />);

it('renders nothing when there is no run', () => {
  open(null);
  expect(screen.queryByRole('dialog')).toBeNull();
});
it('shows key-fact tiles and the run id', () => {
  open();
  const d = screen.getByRole('dialog', { name: 'Run configuration' });
  for (const [label, value] of [['Dataset', 'annomi-sample'], ['Sessions', 'gi, persuade'], ['Attempts / cell', '3'], ['Change goal', 'reduce alcohol use'], ['Language', 'en']]) {
    const tile = within(d).getByText(label).closest('.ui-stat') as HTMLElement;
    expect(within(tile).getByText(value)).toBeTruthy();
  }
  const versions = within(d).getByText('Engine versions').closest('.ui-stat') as HTMLElement;
  expect(versions.textContent).toContain('miti 4.2.1');
  expect(versions.textContent).toContain('abc123');
  expect(within(d).getByText('run_7f3a')).toBeTruthy();
});
it('lists combos with model, tier and effort, without letter tags', () => {
  open();
  const d = screen.getByRole('dialog');
  expect(within(d).queryAllByRole('img', { name: /^Combo / })).toHaveLength(0);
  expect(within(d).getByText('claude-sonnet-4.5')).toBeTruthy();
  expect(within(d).getByText('gpt-5')).toBeTruthy();
  expect(within(d).getAllByText('standard')).toHaveLength(2);
  expect(within(d).getByText('medium')).toBeTruthy();
  expect(within(d).getAllByText('miti').length).toBeGreaterThan(0);
  expect(within(d).queryByText('human')).toBeNull();
});
it('shows no combo letters with 1 or 2+ AI engines (they would mismatch the Compare legend)', () => {
  for (const engines of [['miti', 'human'], ['miti', 'oneshot:miti', 'human']]) {
    const { unmount } = open(run({ engines }));
    expect(screen.queryAllByRole('img', { name: /^Combo / })).toHaveLength(0);
    unmount();
  }
});
it('lists legacy combos by label', () => {
  open(run({ combos: null, legacy_selection: true, combo_keys: ['preset:default'], combo_labels: { 'preset:default': 'preset: default (legacy)' } }));
  expect(screen.getByText('preset: default (legacy)')).toBeTruthy();
  expect(screen.queryByRole('img', { name: 'Combo A' })).toBeNull();
});
it('hides raw JSON until the disclosure is toggled, and omits private refs', () => {
  open(run({ description: '<script>x</script>', ...({ output_ref: 'private-location' } as object) }));
  const d = screen.getByRole('dialog');
  expect(within(d).queryByRole('textbox')).toBeNull();
  expect(d.textContent).not.toContain('"engines"');
  fireEvent.click(within(d).getByRole('button', { name: 'Show raw JSON' }));
  const json = within(d).getByRole('textbox').textContent!;
  expect(JSON.parse(json).engine_git_sha).toEqual({ miti: 'abc123' });
  expect(json).toContain('<script>x</script>');
  expect(d.textContent).not.toContain('private-location');
  expect(document.querySelector('script')).toBeNull();
});
it('Copy writes the saved configuration JSON even while collapsed', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  open();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Copy' }));
  await screen.findByText('Copied.');
  expect(JSON.parse(writeText.mock.calls[0][0]).repeats).toBe(3);
});
it('reports a clipboard failure', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
  open();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Copy' }));
  await screen.findByText('Could not copy. Expand the raw JSON and select it to copy manually.');
});
it('closes via Escape', async () => {
  const onClose = vi.fn();
  open(run(), onClose);
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  await waitFor(() => expect(onClose).toHaveBeenCalled());
});
it('uses an upload label and tolerates missing optional fields', () => {
  open(run({ input: { upload_id: 'u1' }, change_goal: undefined, language: undefined, engine_versions: {}, engine_git_sha: {}, combos: null, combo_keys: [], legacy_selection: false }));
  const d = screen.getByRole('dialog');
  expect(within(d).getByText('Uploaded recording')).toBeTruthy();
  expect(within(d).queryByText('Combos')).toBeNull();
});
