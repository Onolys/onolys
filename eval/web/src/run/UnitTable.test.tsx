// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi, type RunDetail, type RunUnit } from '../api';
import { UnitTable } from './UnitTable';

afterEach(cleanup);
const base = { run_id: 'r1', status: 'partial', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'd', session_ids: ['s1'] }, engines: ['miti', 'human'], selection: null, combos: null, repeats: 3, total_units: 4, completed_units: 4, done_units: 2, failed_units: 1, cancelled_units: 0, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: null, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {} };
const combo = (model: string, tier: string, effort: string) => ({ model, tier, effort });
const units: RunUnit[] = [
  { unit_id: 'u-b', session_id: 's2', engine: 'miti', combo: combo('claude', 'sonnet', 'high'), repeat: 1, status: 'done', stage: 'saved' },
  { unit_id: 'u-a', session_id: 's1', engine: 'miti', combo: combo('gemini', 'pro', 'low'), repeat: 0, status: 'failed', stage: 'coding', error: { code: 'invalid_parameters' } },
  { unit_id: 'human-1', session_id: 's3', engine: 'human', repeat: 0, status: 'done' },
  { unit_id: 'u-c', session_id: 's4', engine: 'miti', combo: combo('claude', 'opus', 'mid'), repeat: 2, status: 'running', stage: 'coding' },
];
const run = (): RunDetail => ({ ...base, units } as unknown as RunDetail);
const show = (r = run(), api = createEvalApi('', vi.fn())) => render(<UnitTable api={api} runId="r1" run={r} />);
const sessions = () => screen.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[0].textContent);

it('headers are plain headers (no buttons) and every column is sortable both ways', () => {
  show();
  const heads = screen.getAllByRole('columnheader');
  expect(heads.map(h => h.textContent)).toEqual(['Session', 'Engine', 'Model', 'Tier', 'Effort', 'Attempt', 'Status', 'Stage', 'Result']);
  for (const h of heads) { expect(h.querySelector('button')).toBeNull(); expect(h.getAttribute('aria-sort')).toBe('none'); }
  for (const [i, h] of heads.entries()) {
    fireEvent.click(h); expect(h.getAttribute('aria-sort')).toBe('ascending');
    const asc = screen.getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[i].textContent);
    fireEvent.click(h); expect(h.getAttribute('aria-sort')).toBe('descending');
    const desc = screen.getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[i].textContent);
    expect(desc.length).toBe(4); expect(asc.length).toBe(4);
    fireEvent.click(h);
  }
  fireEvent.click(heads[0]); expect(sessions()).toEqual(['s1', 's2', 's3', 's4']);
  fireEvent.click(heads[0]); expect(sessions()).toEqual(['s4', 's3', 's2', 's1']);
});
it('hides the search box on a small table', () => {
  show();
  expect(screen.queryByRole('searchbox')).toBeNull();
});
it('filters by status, engine and model', () => {
  show();
  fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'done' } });
  expect(sessions()).toEqual(['s2', 's3']);
  fireEvent.change(screen.getByLabelText('Filter by engine'), { target: { value: 'human' } });
  expect(sessions()).toEqual(['s3']);
  fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('Filter by engine'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('Filter by model'), { target: { value: 'claude' } });
  expect(sessions()).toEqual(['s2', 's4']);
});
it('shows statuses as chips, truncates with a title, tones failed rows, labels human attempts Once', () => {
  show();
  const failed = screen.getAllByRole('row').find(r => r.textContent?.includes('s1'))!;
  expect(failed.className).toContain('ui-row-danger');
  expect(failed.querySelector('.ui-chip-danger')).toBeTruthy();
  expect(within(failed).getAllByRole('cell')[2].getAttribute('title')).toBe('gemini');
  const human = screen.getAllByRole('row').find(r => r.textContent?.includes('s3'))!;
  expect(within(human).getByText('Once')).toBeTruthy();
  expect(screen.getAllByRole('table')[0].textContent).toContain('2 / 3');
});
it('result cell: failed shows an error-code badge; done shows View JSON with no id', () => {
  show();
    expect(screen.getByText('invalid_parameters').closest('.ui-chip-danger')).toBeTruthy();
  const buttons = screen.getAllByRole('button', { name: 'View JSON' });
  expect(buttons).toHaveLength(2);
  for (const b of buttons) expect(b.textContent).not.toMatch(/u-b|human-1/);
});
it('View JSON opens a popup that shows the unit id (copyable) and the output', async () => {
  const api = { ...createEvalApi('', vi.fn()), output: vi.fn().mockResolvedValue({ stored: true }) };
  show(run(), api);
  const row = screen.getAllByRole('row').find(r => r.textContent?.includes('s2'))!;
  fireEvent.click(within(row).getByRole('button', { name: 'View JSON' }));
  await act(async () => {});
  expect(api.output).toHaveBeenCalledWith('r1', 'u-b', expect.any(AbortSignal));
  const dialog = screen.getByRole('dialog', { name: 'Unit output' });
  expect(within(dialog).getByText('u-b')).toBeTruthy();
  expect(within(dialog).getByRole('button', { name: 'Copy unit id' })).toBeTruthy();
  expect(within(dialog).getByText(/"stored": true/)).toBeTruthy();
});
it('has an explainer and a muted footnote, and a fixed-layout table with no scroll wrapper', () => {
  show();
  expect(screen.getByRole('heading', { name: 'Unit progress' })).toBeTruthy();
  expect(document.querySelector('.run-units .ui-note')?.textContent).toContain('error code');
  expect(document.querySelector('.run-units-explainer')?.textContent).toContain('One unit =');
  expect(document.querySelector('.run-units')?.textContent).not.toMatch(/runs done/);
  expect(document.querySelector('.ui-table')).toBeTruthy();
});
it('gives short sortable headers enough width not to truncate (Tier, Effort, Attempt)', () => {
  show();
  const width = (name: string) => parseFloat(screen.getByRole('columnheader', { name }).style.width);
  expect(width('Tier')).toBeGreaterThanOrEqual(7);
  expect(width('Effort')).toBeGreaterThanOrEqual(9);
  expect(width('Attempt')).toBeGreaterThanOrEqual(10);
  const total = screen.getAllByRole('columnheader').reduce((sum, h) => sum + parseFloat(h.style.width), 0);
  expect(total).toBe(100);
});
