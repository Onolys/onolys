// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { History, RunView } from './Runs';
import { ApiError, createEvalApi, type RunDetail, type RunSummary } from './api';
afterEach(() => { cleanup(); vi.useRealTimers(); });
const summary = (): RunSummary => ({ run_id: 'r1', status: 'done', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['human', 'miti'], presets: ['default'], selection: null, combos: null, combo_keys: ['preset:default'], combo_labels: { 'preset:default': 'preset: default (legacy)' }, repeats: 3, total_units: 4, completed_units: 4, done_units: 3, failed_units: 1, cancelled_units: 0, usage: { input_tokens: 10, output_tokens: 4 }, cost_usd_est: .012, unpriced_units: 1, engine_versions: { miti: '1.2' }, engine_git_sha: { miti: 'abc123' }, resolved_presets: { default: { model: 'saved-model' } } });
const detail = (status: RunDetail['status'] = 'done'): RunDetail => ({ ...summary(), status, units: [{ unit_id: 'u1', session_id: 's1', engine: 'miti', preset: 'default', repeat: 0, status: 'done', stage: 'saved' }, { unit_id: 'u3', session_id: 's1', engine: 'miti', preset: 'default', repeat: 2, status: 'failed' }] });
it('Provenance shows the saved resolved combos and base preset', async () => {
 const run = { ...detail(), base_preset: 'configured-prod', resolved_combos: { 'claude/claude-sonnet-5-5/low': { litellm_id: 'saved-combo-model' } } };
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />);
 await act(async () => {});
 fireEvent.click(screen.getByRole('button', { name: 'Config' }));
 fireEvent.click(screen.getByRole('button', { name: 'Show raw JSON' }));
 expect(screen.getByText(/saved-combo-model/)).toBeTruthy(); expect(screen.getByText(/"base_preset": "configured-prod"/)).toBeTruthy();
});
it('does not render the removed embedded comparison or summary', async () => {
 render(<RunView api={{...createEvalApi('', vi.fn()), run:vi.fn().mockResolvedValue(detail())}} runId="r1" onRerun={vi.fn()} />);
 await screen.findByRole('heading', {name:'Run - r1'}); expect(screen.queryByRole('tab', {name:'Summary'})).toBeNull(); expect(screen.queryByRole('heading', {name:'Compare'})).toBeNull();
});
it('polls at 3s, stops terminal, loads JSON lazily as escaped text and aborts unmount', async () => {
 vi.useFakeTimers(); const api = {...createEvalApi('',vi.fn()), run:vi.fn().mockResolvedValueOnce(detail('running')).mockResolvedValue(detail()), output:vi.fn().mockResolvedValue({text:'<img src=x onerror=alert(1)>'})}; const view=render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); await act(async()=>{}); expect(api.run).toHaveBeenCalledTimes(1); await act(async()=>{await vi.advanceTimersByTimeAsync(3000)}); expect(api.run).toHaveBeenCalledTimes(2); await act(async()=>{await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(2); expect(api.output).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button',{name:'View JSON'})); await act(async()=>{}); expect(api.output).toHaveBeenCalledWith('r1','u1',expect.any(AbortSignal)); expect(screen.getByText(/<img src=x/)).toBeTruthy(); expect(document.querySelector('img')).toBeNull(); const signal=api.run.mock.calls[0][1] as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true);
});
it('loads spilled JSON lazily from the detail wire shape with output and private ref omitted', async () => {
  const saved = detail();
  expect(saved.units[0]).not.toHaveProperty('output');
  expect(saved.units[0]).not.toHaveProperty('output_ref');
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(saved), output: vi.fn().mockResolvedValue({ stored: true }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(api.output).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  await act(async () => {});
  expect(api.output).toHaveBeenCalledExactlyOnceWith('r1', 'u1', expect.any(AbortSignal));
  expect(screen.getByText(/"stored": true/)).toBeTruthy();
});
it.each([null, false, 0, ''])('renders inline JSON %j without fetching', async output => {
  const saved = detail();
  saved.units[0] = { ...saved.units[0], output };
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(saved), output: vi.fn() };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  await act(async () => {});
  expect(api.output).not.toHaveBeenCalled();
  expect(within(screen.getByRole('dialog', { name: 'Unit output' })).getByTestId('json-scroll').textContent).toBe(JSON.stringify(output, null, 2));
});
it('refreshes terminal cancellation details before stopping polling', async () => {
  vi.useFakeTimers();
  const cancelled = { ...detail('cancelled'), done_units: 0, completed_units: 4, cancelled_units: 2, units: [{ ...detail().units[0], unit_id: 'cancelled-unit', status: 'cancelled' as const }] };
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValueOnce(detail('running')).mockResolvedValue(cancelled), cancel: vi.fn().mockResolvedValue({ run_id: 'r1', status: 'cancelled' }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel run' }));
  await act(async () => {});
  expect(api.cancel).toHaveBeenCalledWith('r1');
  expect(api.run).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('status', { name: 'Run status' }).textContent).toBe('Cancelled0 of 4 done1 failed2 cancelled');
  expect(screen.queryByRole('button', { name: 'View JSON' })).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
  expect(api.run).toHaveBeenCalledTimes(2);
});
it('keeps polling after cancellation while in-flight work runs, then shows final outputs and costs', async () => {
  vi.useFakeTimers();
  const pending = { ...detail('running'), completed_units: 0, units: [{ ...detail().units[0], status: 'running' as const }], cost_usd_est: 0 };
  const done = { ...detail('done'), cost_usd_est: 0.25 };
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(pending).mockResolvedValue(done), cancel: vi.fn().mockResolvedValue({ run_id: 'r1', status: 'running' }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(screen.queryByRole('button', { name: 'View JSON' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel run' }));
  await act(async () => {});
  expect(api.run).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(3);
  expect(screen.getByRole('status', { name: 'Run status' }).textContent).toBe('Done3 of 4 done1 failed0 cancelled');
  expect(screen.getByRole('button', { name: 'View JSON' })).toBeTruthy();
  expect(screen.getByText(/~\$0.2500/)).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(9000); });
  expect(api.run).toHaveBeenCalledTimes(3);
});
it('history opens a shared config modal and rerun only prefills the saved run', async () => {
 const run = summary(), onRerun = vi.fn();
 const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [run] }), rerun: vi.fn(), start: vi.fn() };
 render(<History api={api} onOpen={vi.fn()} onRerun={onRerun} />);
 await screen.findByRole('link', { name: 'saved' });
 fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for saved' }), { key: 'Enter' });
 fireEvent.click(await screen.findByRole('menuitem', { name: 'Config' }));
 const dialog = screen.getByRole('dialog', { name: 'Run configuration' });
 expect(within(dialog).getByText(/abc123/)).toBeTruthy();
 fireEvent.click(within(dialog).getByRole('button', { name: 'Show raw JSON' }));
 expect(within(dialog).getByText(/saved-model/)).toBeTruthy();
 const copy = vi.fn().mockResolvedValue(undefined);
 Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } });
 fireEvent.click(within(dialog).getByRole('button', { name: 'Copy' }));
 await screen.findByText('Copied.');
 expect(JSON.parse(copy.mock.calls[0][0]).engine_git_sha).toEqual({ miti: 'abc123' });
 fireEvent.keyDown(dialog, { key: 'Escape' });
 await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Actions for saved' })));
 fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for saved' }), { key: 'Enter' });
 fireEvent.click(await screen.findByRole('menuitem', { name: 'Rerun' }));
 expect(onRerun).toHaveBeenCalledWith(run);
 expect(api.rerun).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled();
});
it.each(['done', 'partial', 'failed', 'cancelled'] as const)('does not poll terminal %s runs', async status => {
 vi.useFakeTimers(); const api={...createEvalApi('',vi.fn()),run:vi.fn().mockResolvedValue(detail(status))}; render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); await act(async()=>{}); await act(async()=>{await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(1); expect(screen.queryByRole('button',{name:'Cancel run'})).toBeNull();
});
it('aborts in-flight progress requests on unmount and never schedules another poll', async()=>{
 vi.useFakeTimers(); let resolve!: (value:RunDetail)=>void; const api={...createEvalApi('',vi.fn()),run:vi.fn().mockImplementation(()=>new Promise<RunDetail>(r=>{resolve=r}))}; const view=render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); const signal=api.run.mock.calls[0][1] as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true); await act(async()=>{resolve(detail('running')); await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(1);
});

it('keeps polling with backoff after a failed status poll and shows a non-blocking error', async () => {
  vi.useFakeTimers();
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockRejectedValueOnce(new Error('net down')).mockRejectedValueOnce(new Error('net down')).mockResolvedValueOnce(detail('running')).mockResolvedValue(detail()) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(api.run).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/net down/)).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(3);
  expect(screen.queryByText(/net down/)).toBeNull();
  expect(screen.getByRole('button', { name: 'Cancel run' })).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(4);
  expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull();
});
it('shows the cancelling note and hides Cancel when the run summary says cancel_requested', async () => {
  vi.useFakeTimers();
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue({ ...detail('running'), cancel_requested: true }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull();
  expect(screen.getByText('Cancelled — runs already in progress will finish; no new runs start.')).toBeTruthy();
  expect(screen.getByText('Cancelling')).toBeTruthy();
});
it('history loads more using the server cursor, retains rows on failure and retries that page', async () => {
  const runs = vi.fn().mockResolvedValueOnce({ runs: [summary()], next_cursor: 'page2' }).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ runs: [{ ...summary(), run_id: 'r2' }], next_cursor: null });
  render(<History api={{ ...createEvalApi('', vi.fn()), runs }} onOpen={vi.fn()} onRerun={vi.fn()} />);
  await screen.findByRole('link', { name: 'saved' });
  fireEvent.click(screen.getByRole('button', { name: 'Load more' })); await screen.findByText('offline');
  expect(screen.getAllByRole('link', { name: 'saved' })[0]).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Retry history' })); await act(async () => {});
  expect(screen.getAllByRole('link', { name: 'saved' }).map(link => link.getAttribute('href'))).toEqual(['?run=r1', '?run=r2']);
  expect(runs.mock.calls[1][1]).toBe('page2'); expect(runs.mock.calls[2][1]).toBe('page2');
  expect(screen.getAllByRole('link', { name: 'saved' })[0]).toBeTruthy(); expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
});
it('stops polling a structured HTTP 404 until an explicit retry', async () => {
  vi.useFakeTimers(); const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{"detail":"Run not found"}', { status: 404 }));
  render(<RunView api={createEvalApi('', fetcher)} runId="missing" onRerun={vi.fn()} />); await act(async () => {});
  await act(async () => { await vi.advanceTimersByTimeAsync(90000); }); expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('alert').textContent).not.toContain('Still trying');
  fireEvent.click(screen.getByRole('button', { name: 'Retry run status' })); await act(async () => {}); expect(fetcher).toHaveBeenCalledTimes(2);
});
it('aborts stale history requests on API change and ignores late results', async () => {
  let resolve!: (value: { runs: RunSummary[]; next_cursor: null }) => void;
  const old = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockImplementation(() => new Promise(r => { resolve = r; })) };
  const view = render(<History api={old} onOpen={vi.fn()} onRerun={vi.fn()} />);
  const fresh = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [{ ...summary(), run_id: 'fresh' }], next_cursor: null }) };
  view.rerender(<History api={fresh} onOpen={vi.fn()} onRerun={vi.fn()} />); await screen.findByRole('link', { name: 'saved' });
  expect(old.runs.mock.calls[0][0].aborted).toBe(true);
  await act(async () => { resolve({ runs: [summary()], next_cursor: null }); }); expect(screen.getAllByRole('link', { name: 'saved' })).toHaveLength(1);
  expect(screen.getByRole('link', { name: 'saved' }).getAttribute('href')).toBe('?run=fresh');
});
it('history formats the run date for the locale instead of showing raw ISO', async () => {
  const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }) };
  render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
  expect(await screen.findByText(new Date('2026-11-23T10:00:00Z').toLocaleString())).toBeTruthy();
  expect(screen.queryByText('2026-11-23T10:00:00Z')).toBeNull();
});
it('history searches the complete saved configuration across cursor pages without fetching details', async () => {
 const remote = { ...summary(), run_id: 'remote', name: 'Evening', description: 'Rare metadata', selection: { models: ['Claude'], tiers: ['Sonnet'], efforts: ['high'] }, resolved_combos: { saved: { temperature: 0.12345 } } };
 const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValueOnce({ runs: [summary()], next_cursor: 'tail' }).mockResolvedValueOnce({ runs: [remote] }), run: vi.fn() };
 render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await screen.findByRole('link', { name: 'saved' });
 fireEvent.change(screen.getByLabelText('Search history'), { target: { value: 'RARE METADATA' } });
 await screen.findByRole('button', { name: 'Actions for Evening' });
 expect(api.runs.mock.calls[1][1]).toBe('tail'); expect(api.run).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Search history'), { target: { value: '0.12345' } });
 expect(screen.getAllByRole('link', { name: 'saved' })).toHaveLength(1);
 fireEvent.change(screen.getByLabelText('Search history'), { target: { value: '' } });
 for (const name of ['Date', 'Dataset', 'Status', 'Engines', 'Models', 'Tiers', 'Efforts']) {
   if (name !== 'Date') expect(screen.getByLabelText(`Filter ${name}`)).toBeTruthy();
   const column = screen.getByRole('columnheader', { name });
   fireEvent.click(within(column).getByRole('button'));
   expect(column.getAttribute('aria-sort')).toBe('ascending');
   fireEvent.click(within(column).getByRole('button'));
   expect(column.getAttribute('aria-sort')).toBe('descending');
 }
 fireEvent.change(screen.getByLabelText('Filter Models'), { target: { value: 'claude' } });
 expect(screen.getAllByRole('link', { name: 'saved' })).toHaveLength(1);
 fireEvent.change(screen.getByLabelText('Date from'), { target: { value: '2026-11-24' } });
 expect(screen.queryAllByRole('link')).toHaveLength(0);
});
it('history uses native run links with ordinary-click SPA navigation', async () => {
 const onOpen = vi.fn();
 render(<History api={{ ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }) }} onOpen={onOpen} onRerun={vi.fn()} />);
 const link = await screen.findByRole('link', { name: 'saved' });
 expect(link.getAttribute('href')).toContain('?run=r1');
 fireEvent.click(link, { ctrlKey: true }); expect(onOpen).not.toHaveBeenCalled();
 fireEvent.click(link); expect(onOpen).toHaveBeenCalledExactlyOnceWith('r1');
 expect(screen.queryByRole('columnheader', { name: 'ID' })).toBeNull();
});
it('detail names runs and labels unit configuration and repeated attempts in a compact table', async () => {
 const run = { ...detail(), name: 'Morning', combos: [{ model: 'claude', tier: 'sonnet', effort: 'high' }], combo_keys: ['claude/sonnet/high'], units: detail().units.map(unit => ({ ...unit, preset: null, combo: { model: 'claude', tier: 'sonnet', effort: 'high' }, combo_key: 'claude/sonnet/high' })) };
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />);
 await screen.findByRole('heading', { name: 'Run - Morning' });
 const table = screen.getByRole('table');
 expect(table.textContent).toContain('sonnet'); expect(table.textContent).toContain('1 / 3'); expect(table.textContent).toContain('3 / 3');
 expect(screen.queryByText('Saved configuration and versions', { selector: 'summary' })).toBeNull();
});

it('automatically drains every history page for a filter and aborts the active page on unmount', async () => {
 let pageSignal: AbortSignal | undefined;
 const runs = vi.fn().mockResolvedValueOnce({ runs: [summary()], next_cursor: 'p2' })
   .mockResolvedValueOnce({ runs: [{ ...summary(), run_id: 'r2' }], next_cursor: 'p3' })
   .mockImplementationOnce((signal: AbortSignal) => { pageSignal = signal; return new Promise(() => {}); });
 const view = render(<History api={{ ...createEvalApi('', vi.fn()), runs }} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await screen.findByRole('link', { name: 'saved' });
 fireEvent.change(screen.getByLabelText('Filter Status'), { target: { value: 'DONE' } });
 await screen.findByText('Loading full history for search, filters and sorting…');
 await waitFor(() => expect(runs).toHaveBeenCalledTimes(3));
 expect(runs.mock.calls.map(call => call[1])).toEqual([undefined, 'p2', 'p3']);
 view.unmount(); expect(pageSignal?.aborted).toBe(true);
});
it('full-history search keeps partial rows on a failed page and retries the same cursor', async () => {
 const runs = vi.fn().mockResolvedValueOnce({ runs: [summary()], next_cursor: 'p2' })
   .mockRejectedValueOnce(new Error('Page unavailable'))
   .mockResolvedValueOnce({ runs: [{ ...summary(), run_id: 'r2' }], next_cursor: null });
 render(<History api={{ ...createEvalApi('', vi.fn()), runs }} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await screen.findByRole('link', { name: 'saved' });
 fireEvent.change(screen.getByLabelText('Search history'), { target: { value: 'saved' } });
 expect((await screen.findByRole('alert')).textContent).toContain('Results are incomplete');
 expect(screen.getAllByRole('link', { name: 'saved' })).toHaveLength(1);
 fireEvent.click(screen.getByRole('button', { name: 'Retry history' }));
 await screen.findByText('All 2 saved runs searched.');
 expect(screen.getAllByRole('link', { name: 'saved' })).toHaveLength(2);
 expect(runs.mock.calls.map(call => call[1])).toEqual([undefined, 'p2', 'p2']);
});
it('config omits private run references and offers manual copying on clipboard failure', async () => {
 const run = { ...detail(), output_ref: 'private-storage-location', description: '<script>unsafe</script>' };
 Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />);
 fireEvent.click(await screen.findByRole('button', { name: 'Config' }));
 const dialog = screen.getByRole('dialog');
 fireEvent.click(within(dialog).getByRole('button', { name: 'Show raw JSON' }));
 expect(dialog.textContent).not.toContain('private-storage-location');
 expect(within(dialog).getByRole('textbox').textContent).toContain('<script>unsafe</script>');
 expect(document.querySelector('script')).toBeNull();
 fireEvent.click(within(dialog).getByRole('button', { name: 'Copy' }));
 await screen.findByText('Could not copy. Expand the raw JSON and select it to copy manually.');
});

it.each(['Escape', 'Close'])('restores focus to detail Config after %s dismissal', async dismissal => {
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(detail()) }} runId="r1" onRerun={vi.fn()} />);
 const trigger = await screen.findByRole('button', { name: 'Config' });
 trigger.focus(); fireEvent.click(trigger);
 const dialog = await screen.findByRole('dialog');
 await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
 if (dismissal === 'Escape') fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
 else fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
 await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
 await waitFor(() => expect(document.activeElement).toBe(trigger));
});
it.each(['Escape', 'Close'])('opens Config by keyboard without losing dialog focus and returns to row actions after %s', async dismissal => {
 render(<History api={{ ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }) }} onOpen={vi.fn()} onRerun={vi.fn()} />);
 const trigger = await screen.findByRole('button', { name: 'Actions for saved' });
 trigger.focus(); fireEvent.keyDown(trigger, { key: 'Enter' });
 const config = await screen.findByRole('menuitem', { name: 'Config' });
 config.focus(); fireEvent.keyDown(config, { key: 'Enter' });
 const dialog = await screen.findByRole('dialog');
 await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
 expect(dialog.contains(document.activeElement)).toBe(true);
 if (dismissal === 'Escape') fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
 else fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
 await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
 await waitFor(() => expect(document.activeElement).toBe(trigger));
});
it('filters by the same local calendar date shown for a run near midnight', async () => {
 // Run this test in America/Los_Angeles too: local late evening is the next UTC day.
 const created_at = new Date(2026, 10, 23, 23, 30).toISOString();
 render(<History api={{ ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [{ ...summary(), created_at }] }) }} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await screen.findByText(new Date(created_at).toLocaleString());
 fireEvent.change(screen.getByLabelText('Date from'), { target: { value: '2026-11-23' } });
 fireEvent.change(screen.getByLabelText('Date to'), { target: { value: '2026-11-23' } });
 expect(screen.getByRole('link', { name: 'saved' })).toBeTruthy();
 fireEvent.change(screen.getByLabelText('Date from'), { target: { value: '2026-11-24' } });
 expect(screen.queryByRole('link', { name: 'saved' })).toBeNull();
});
it('labels a Human unit as Once while model attempts use the configured repeat count', async () => {
 const run = detail(); run.units.push({ unit_id: 'human', session_id: 's1', engine: 'human', repeat: 0, status: 'done' });
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />);
 await screen.findByRole('cell', { name: 'Once' });
 const row = screen.getByRole('cell', { name: 'Once' }).closest('tr')!;
 expect(within(row).getByRole('cell', { name: 'Once' })).toBeTruthy();
 expect(screen.getByRole('table').textContent).toContain('3 / 3');
});
const openActions = async (name = 'saved') => {
 await screen.findByRole('link', { name });
 fireEvent.keyDown(screen.getByRole('button', { name: `Actions for ${name}` }), { key: 'Enter' });
};
it('Delete is enabled for terminal runs and disabled while active or deleting', async () => {
 for (const [status, enabled] of [['done', true], ['partial', true], ['failed', true], ['cancelled', true], ['queued', false], ['running', false], ['deleting', false]] as const) {
  const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [{ ...summary(), status }] }) };
  const view = render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
  await openActions();
  const item = await screen.findByRole('menuitem', { name: 'Delete' });
  expect(item.getAttribute('aria-disabled') === 'true' || item.hasAttribute('data-disabled')).toBe(!enabled);
  view.unmount();
 }
});
it('Delete confirm states counts and what stays, posts the run id, then shows deleting', async () => {
 const deleteRun = vi.fn().mockResolvedValue({ run_id: 'r1', status: 'deleting' });
 const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }), deleteRun };
 render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await openActions();
 fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
 const dialog = await screen.findByRole('dialog', { name: /Delete run/ });
 expect(dialog.textContent).toContain('4 runs, 3 reports, 3 output files; datasets, gold and sessions stay');
 expect(deleteRun).not.toHaveBeenCalled();
 fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
 expect(deleteRun).not.toHaveBeenCalled();
 await openActions();
 fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
 fireEvent.click(within(await screen.findByRole('dialog', { name: /Delete run/ })).getByRole('button', { name: 'Delete' }));
 await waitFor(() => expect(deleteRun).toHaveBeenCalledExactlyOnceWith('r1'));
 await waitFor(() => expect(screen.getByText('deleting')).toBeTruthy());
});
it('Delete shows a run_active refusal and keeps the row', async () => {
 const deleteRun = vi.fn().mockRejectedValue(new ApiError('Run is still active.', 409));
 const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }), deleteRun };
 render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
 await openActions();
 fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
 fireEvent.click(within(await screen.findByRole('dialog', { name: /Delete run/ })).getByRole('button', { name: 'Delete' }));
 expect((await screen.findByRole('alert')).textContent).toContain('Run is still active.');
 expect(screen.getByText('done')).toBeTruthy();
});
it('deleteRun posts confirm_run_id to /runs/{id}/delete', async () => {
 const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ run_id: 'r 1', status: 'deleting' }) });
 await createEvalApi('https://x', fetcher as unknown as typeof fetch).deleteRun('r 1');
 expect(fetcher).toHaveBeenCalledWith('https://x/v1/runs/r%201/delete', expect.objectContaining({ method: 'POST', body: JSON.stringify({ confirm_run_id: 'r 1' }) }));
});
it.each(['done','partial','queued','running','failed','cancelled','deleting'] as const)('offers Compare only with finished results: %s',async status=>{
 const run={...detail(status),run_id:`entry-${status}`};
 const client={...createEvalApi('',vi.fn()),run:vi.fn().mockResolvedValue(run),runs:vi.fn().mockResolvedValue({runs:[run]})};
 const onNavigate=vi.fn();
 const view=render(<RunView api={client} runId={run.run_id} onRerun={vi.fn()} onNavigate={onNavigate}/>);
 await act(async()=>{});
 if(status==='done'||status==='partial'){
  const link=screen.getByRole('link',{name:'Compare'});expect(link.getAttribute('href')).toContain(`run=entry-${status}&view=compare&tab=overview`);fireEvent.click(link);expect(onNavigate).toHaveBeenCalledWith({run:run.run_id,view:'compare',tab:'overview'});
 }else{expect(screen.queryByRole('link',{name:'Compare'})).toBeNull();const off=screen.getByRole('button',{name:'Compare'});expect((off as HTMLButtonElement).disabled).toBe(true);expect(off.getAttribute('title')).toBe('Compare opens when the run has finished results');}
 view.unmount();
 render(<History api={client} onOpen={vi.fn()} onRerun={vi.fn()} onNavigate={onNavigate}/>);await act(async()=>{});
 expect(Boolean(screen.queryByRole('link',{name:'Compare'}))).toBe(status==='done'||status==='partial');
});
