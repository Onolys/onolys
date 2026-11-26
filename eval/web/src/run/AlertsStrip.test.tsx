// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import type { RunDetail } from '../api';
import { AlertsStrip } from './AlertsStrip';

afterEach(cleanup);
const base = { run_id: 'r1', name: 'Morning', status: 'cancelled', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['miti'], selection: null, combos: null, legacy_selection: true, combo_keys: [], combo_labels: {}, repeats: 1, total_units: 4, completed_units: 0, done_units: 0, failed_units: 0, cancelled_units: 4, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: null, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, units: [] } as unknown as RunDetail;

it('says so when a run was cancelled with nothing completed', () => {
  render(<AlertsStrip run={base} />);
  expect(screen.getByText('Cancelled — no runs completed.')).toBeTruthy();
});
it('renders nothing for a plain done run', () => {
  const { container } = render(<AlertsStrip run={{ ...base, status: 'done', done_units: 4, cancelled_units: 0 }} />);
  expect(container.firstChild).toBeNull();
});
