// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { History, RunView } from './Runs';
import { ApiError, createEvalApi, type RunDetail, type RunStatus } from './api';
afterEach(() => { cleanup(); vi.useRealTimers(); });
const run = (status: RunStatus = 'running'): RunDetail => ({ run_id: 'r1', name: 'Morning', status, created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['miti'], selection: null, combos: null, legacy_selection: true, combo_keys: [], combo_labels: {}, repeats: 1, total_units: 7, completed_units: 4, done_units: 3, failed_units: 1, cancelled_units: 0, usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: null, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, units: [] });
const apiFor = (value = run()) => ({ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(value), runs: vi.fn().mockResolvedValue({ runs: [value] }), cancel: vi.fn().mockResolvedValue({ run_id: 'r1', status: 'running' }) });
async function openCancel(page: string) {
 if (page === 'detail') { const button = await screen.findByRole('button', { name: 'Cancel run' }); button.focus(); fireEvent.click(button); return button; }
 const trigger = await screen.findByRole('button', { name: 'Actions for Morning' }); trigger.focus(); fireEvent.keyDown(trigger, { key: 'Enter' });
 const item = await screen.findByRole('menuitem', { name: 'Cancel run' }); item.focus(); fireEvent.keyDown(item, { key: 'Enter' }); return trigger;
}
it.each(['detail', 'history'])('%s confirms cancellation with dialog focus and returns focus after Escape without a POST', async page => {
 const api = apiFor(); render(page === 'detail' ? <RunView api={api} runId="r1" onRerun={vi.fn()} /> : <History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
 const trigger = await openCancel(page); const dialog = await screen.findByRole('dialog', { name: 'Stop this eval run?' });
 expect(dialog.textContent).toContain('Runs already finished are kept and can be compared. Runs already in progress will finish; no new runs start.');
 await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
 const close = within(dialog).getByRole('button', { name: 'Close' }); close.focus(); fireEvent.keyDown(close, { key: 'Tab' }); expect(dialog.contains(document.activeElement)).toBe(true);
 fireEvent.keyDown(document.activeElement!, { key: 'Escape' }); await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()); await waitFor(() => expect(document.activeElement).toBe(trigger)); expect(api.cancel).not.toHaveBeenCalled();
});
it.each(['queued', 'running', 'done', 'partial', 'failed', 'cancelled', 'deleting'] as const)('offers cancel only on active %s runs', async status => {
 const api = apiFor(run(status)); const view = render(<RunView api={api} runId="r1" onRerun={vi.fn()} />); await act(async () => {});
 expect(Boolean(screen.queryByRole('button', { name: 'Cancel run' }))).toBe(['queued', 'running'].includes(status)); view.unmount();
 render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); fireEvent.keyDown(await screen.findByRole('button', { name: 'Actions for Morning' }), { key: 'Enter' }); await screen.findByRole('menuitem', { name: 'Config' });
 expect(Boolean(screen.queryByRole('menuitem', { name: 'Cancel run' }))).toBe(['queued', 'running'].includes(status));
});
it.each(['detail', 'history'])('%s guards duplicate cancel clicks, shows pending copy and clears it when terminal', async page => {
 let resolve!: (value: { run_id: string; status: string }) => void;
 const api = apiFor(); api.cancel.mockImplementation(() => new Promise(r => { resolve = r; }));
 render(page === 'detail' ? <RunView api={api} runId="r1" onRerun={vi.fn()} /> : <History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await openCancel(page);
 const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel run' }); fireEvent.click(confirm); fireEvent.click(confirm); expect(api.cancel).toHaveBeenCalledExactlyOnceWith('r1');
 await act(async () => { resolve({ run_id: 'r1', status: 'running' }); });
 expect(screen.getByText('Cancelled — runs already in progress will finish; no new runs start.')).toBeTruthy(); expect(screen.getByText(/cancelling/)).toBeTruthy();
 api.run.mockResolvedValue(run('done')); await waitFor(() => expect(screen.queryByText('Cancelled — runs already in progress will finish; no new runs start.')).toBeNull(), { timeout: 4000 });
});
it.each(['detail', 'history'])('%s retries cancellation errors and handles 409 with a fresh read', async page => {
 const api = apiFor(); api.cancel.mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new ApiError('Already finished', 409));
 render(page === 'detail' ? <RunView api={api} runId="r1" onRerun={vi.fn()} /> : <History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await openCancel(page);
 fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel run' })); expect((await screen.findByRole('alert')).textContent).toContain('offline'); api.run.mockResolvedValue(run('done'));
 fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Retry' })); await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()); expect(screen.queryByRole('alert')).toBeNull(); expect(screen.queryByText(/cancelling/)).toBeNull(); expect(api.cancel).toHaveBeenCalledTimes(2);
});
it('history refreshes active rows through GETs every 3 seconds then stops and aborts on unmount', async () => {
 vi.useFakeTimers(); const fetcher = vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith('/runs') ? { runs: [run()] } : run('done')))));
 const view = render(<History api={createEvalApi('', fetcher)} onOpen={vi.fn()} onRerun={vi.fn()} />); await act(async () => {}); expect(fetcher).toHaveBeenCalledTimes(1);
 await act(async () => { await vi.advanceTimersByTimeAsync(2999); }); expect(fetcher).toHaveBeenCalledTimes(1); await act(async () => { await vi.advanceTimersByTimeAsync(1); }); expect(fetcher).toHaveBeenCalledTimes(2); expect(screen.getByText('done')).toBeTruthy();
 await act(async () => { await vi.advanceTimersByTimeAsync(9000); }); expect(fetcher).toHaveBeenCalledTimes(2); expect(fetcher.mock.calls.every(call => !call[1]?.method || call[1].method === 'GET')).toBe(true); view.unmount(); expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
});
it('hides cancellation when already requested and aborts an in-flight history refresh', async () => {
 vi.useFakeTimers(); const api = apiFor({ ...run(), cancel_requested: true }); api.run.mockImplementation(() => new Promise(() => {})); const view = render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />); await act(async () => {});
 fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for Morning' }), { key: 'Enter' }); await act(async () => {}); expect(screen.queryByRole('menuitem', { name: 'Cancel run' })).toBeNull();
 await act(async () => { await vi.advanceTimersByTimeAsync(3000); }); const signal = api.run.mock.calls[0][1] as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true);
});
it('uses one cancel POST for duplicate confirm clicks and accepts a terminal no-op response', async () => {
 const fetcher = vi.fn().mockImplementation((_url: string, init?: RequestInit) => Promise.resolve(new Response(JSON.stringify(init?.method === 'POST' ? { run_id: 'r1', status: 'done' } : fetcher.mock.calls.length === 1 ? run() : run('done')))));
 render(<RunView api={createEvalApi('', fetcher)} runId="r1" onRerun={vi.fn()} />); await openCancel('detail');
 const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel run' }); fireEvent.click(confirm); fireEvent.click(confirm);
 await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
 const posts = fetcher.mock.calls.filter(call => call[1]?.method === 'POST'); expect(posts).toHaveLength(1); expect(posts[0][0]).toBe('/v1/runs/r1/cancel'); expect(screen.getByText(/^done ·/)).toBeTruthy(); expect(screen.queryByRole('alert')).toBeNull();
});
