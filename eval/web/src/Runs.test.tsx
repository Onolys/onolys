// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CompareView, History, RunView, SummaryView } from './Runs';
import { NewRun } from './NewRun';
import { createEvalApi, type Compare, type RunDetail, type RunSummary } from './api';
afterEach(() => { cleanup(); vi.useRealTimers(); });
const ids = ['giving_information', 'persuade', 'persuade_with_permission', 'question', 'simple_reflection', 'complex_reflection', 'affirm', 'seeking_collaboration', 'emphasizing_autonomy', 'confront', 'cultivating_change_talk', 'softening_sustain_talk', 'partnership', 'empathy', 'reflection_question_ratio', 'pct_cr'];
const mkAgg = (combo: string, label: string, mae: number | null, extra: Record<string, unknown> = {}) => ({ engine: 'miti', combo_key: combo, label, n: 2, failed: 0, within_1: { empathy: { n: 2, total: 4, fraction: .5 } }, usage: { input_tokens: 100, output_tokens: 20, calls: 3 }, cost_usd_est: .01, metrics: { n: 2, counts: { giving_information: { mae, mean_bias: 0, n: 2 } }, globals: { empathy: { mae, mean_bias: 0, n: 2, within_1: { n: 2, total: 4, fraction: .5 } } }, summaries: {} }, ...extra });
const comparison = (human = true): Compare => ({ has_human: human, metrics: ids.map((id, i) => ({ id, label: id, group: i < 10 ? 'counts' : i < 14 ? 'globals' : 'summaries' })), sessions: [{ session_id: 's1', human: human ? Object.fromEntries(ids.map(id => [id, 2])) : null, cells: [{ engine: 'miti', combo_key: 'preset:default', label: 'preset: default (legacy)', n: 2, failed: 1, error_code: 'HTTP_500', unit_ids: ['u1', 'u2', 'u3'], values: Object.fromEntries(ids.map(id => [id, { mean: id === 'reflection_question_ratio' ? null : id === 'pct_cr' ? .75 : 2, min: 1, max: 3, n: id === 'reflection_question_ratio' ? 0 : 2 }])), ...(human ? { diff: { giving_information: 0 } } : {}), error: human ? { giving_information: { mae: 1.5, mean_bias: 0, n: 2 } } : null }] }], aggregates: human ? [mkAgg('preset:default', 'preset: default (legacy)', 1)] : [], notes: [] });
const summary = (): RunSummary => ({ run_id: 'r1', status: 'done', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['human', 'miti'], presets: ['default'], selection: null, combos: null, legacy_selection: true, combo_keys: ['preset:default'], combo_labels: { 'preset:default': 'preset: default (legacy)' }, repeats: 3, total_units: 4, completed_units: 4, done_units: 3, failed_units: 1, cancelled_units: 0, usage: { input_tokens: 10, output_tokens: 4 }, cost_usd_est: .012, unpriced_units: 1, engine_versions: { miti: '1.2' }, engine_git_sha: { miti: 'abc123' }, resolved_presets: { default: { model: 'saved-model' } } });
const detail = (status: RunDetail['status'] = 'done'): RunDetail => ({ ...summary(), status, units: [{ unit_id: 'u1', session_id: 's1', engine: 'miti', preset: 'default', repeat: 0, status: 'done', stage: 'saved' }, { unit_id: 'u3', session_id: 's1', engine: 'miti', preset: 'default', repeat: 2, status: 'failed' }], compare: comparison() });
it('Provenance shows the saved resolved combos and base preset', async () => {
 const run = { ...detail(), base_preset: 'configured-prod', resolved_combos: { 'claude/claude-sonnet-5-5/low': { litellm_id: 'saved-combo-model' } } };
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(run) }} runId="r1" onRerun={vi.fn()} />);
 await act(async () => {});
 expect(screen.getByText(/saved-combo-model/)).toBeTruthy(); expect(screen.getByText(/"base_preset": "configured-prod"/)).toBeTruthy();
});
it('transposes: Human row first, metrics as columns, value + diff + session error, failures with code', () => {
 render(<CompareView compare={comparison()} />);
 const heads = screen.getAllByRole('columnheader').map(e => e.textContent);
 expect(heads).toHaveLength(17); expect(heads.slice(0, 3)).toEqual(['Engine / combo', 'giving_information', 'persuade']);
 const rows = screen.getAllByRole('row'); expect(rows).toHaveLength(3);
 expect(rows[1].textContent).toMatch(/^Human/); expect(rows[1].textContent).toContain('2, n=1');
 expect(rows[2].textContent).toContain('miti · preset: default (legacy)');
 expect(rows[2].textContent).toContain('1 failed'); expect(rows[2].textContent).toContain('HTTP_500');
 const cells = rows[2].querySelectorAll('td'); expect(cells[0].textContent).toContain('2 (1–3), n=2'); expect(cells[0].textContent).toContain('diff 0'); expect(cells[0].textContent).toContain('MAE 1.5');
 expect(rows[2].textContent).toContain('—, n=0'); expect(rows[2].textContent).toContain('75%');
 expect(screen.getByRole('table').closest('.table-scroll')).toBeTruthy();
});
it('omits Human row, diff and error without reference; pending Human shows n=0', () => {
 const view = render(<CompareView compare={comparison(false)} />); expect(screen.queryByText('Human')).toBeNull(); expect(screen.queryByText(/MAE/)).toBeNull(); expect(screen.queryByText(/diff/)).toBeNull(); expect(screen.queryByRole('tab', { name: 'Summary' })).toBeNull();
 const pending = comparison(); pending.sessions[0].human = null; view.rerender(<CompareView compare={pending} />); expect(screen.getAllByRole('row')[1].textContent).toContain('—, n=0');
});
it('selects sessions for signed differences', () => {
 const data = comparison(); data.sessions.push({...data.sessions[0], session_id:'s2', cells:[{...data.sessions[0].cells[0], diff:{giving_information:-3}}]}); render(<CompareView compare={data} />); fireEvent.change(screen.getByLabelText('Session'),{target:{value:'s2'}}); expect(screen.getByRole('table').textContent).toContain('diff -3');
});
it('Summary: sorts by any column, highlights best MAE per column, shows legacy label and globals within_1', () => {
 const data = comparison(); data.aggregates = [mkAgg('a/x', 'a/x', 2, { failed: 1 }), mkAgg('b/y', 'b/y', 1), mkAgg('preset:default', 'preset: default (legacy)', 3)];
 render(<SummaryView compare={data} />);
 const names = () => screen.getAllByRole('rowheader').map(e => e.textContent);
 expect(names()).toEqual(['miti · a/x', 'miti · b/y', 'miti · preset: default (legacy)']);
 const col = screen.getByRole('columnheader', { name: /giving_information/ }); expect(col.getAttribute('aria-sort')).toBe('none');
 fireEvent.click(screen.getByRole('button', { name: /giving_information/ }));
 expect(names()[0]).toBe('miti · b/y'); expect(col.getAttribute('aria-sort')).toBe('ascending');
 fireEvent.click(screen.getByRole('button', { name: /giving_information/ }));
 expect(names()[0]).toBe('miti · preset: default (legacy)'); expect(col.getAttribute('aria-sort')).toBe('descending');
 const best = document.querySelectorAll('td[data-best="true"]'); expect(best.length).toBeGreaterThan(0);
 const row = screen.getByRole('row', { name: /b\/y/ }); expect(row.querySelector('td[data-best="true"]')?.textContent).toContain('1');
 expect(screen.getByRole('row', { name: /a\/x/ }).querySelector('td[data-best="true"]')).toBeNull();
 expect(row.textContent).toContain('0.5'); expect(row.textContent).toContain('120'); expect(row.textContent).toContain('$0.0100');
});
it('shows Summary tab only with Human reference and switches to it', () => {
 render(<RunView api={{ ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(detail()) }} runId="r1" onRerun={vi.fn()} />);
 return screen.findByRole('tab', { name: 'Summary' }).then(tab => { fireEvent.click(tab); expect(screen.getByRole('table').textContent).toContain('preset: default (legacy)'); });
});
it('polls at 3s, stops terminal, loads JSON lazily as escaped text and aborts unmount', async () => {
 vi.useFakeTimers(); const api = {...createEvalApi('',vi.fn()), run:vi.fn().mockResolvedValueOnce(detail('running')).mockResolvedValue(detail()), output:vi.fn().mockResolvedValue({text:'<img src=x onerror=alert(1)>'})}; const view=render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); await act(async()=>{}); expect(api.run).toHaveBeenCalledTimes(1); await act(async()=>{await vi.advanceTimersByTimeAsync(3000)}); expect(api.run).toHaveBeenCalledTimes(2); await act(async()=>{await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(2); expect(api.output).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button',{name:'View JSON u1'})); await act(async()=>{}); expect(api.output).toHaveBeenCalledWith('r1','u1',expect.any(AbortSignal)); expect(screen.getByText(/<img src=x/)).toBeTruthy(); expect(document.querySelector('img')).toBeNull(); const signal=api.run.mock.calls[0][1] as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true);
});
it('loads spilled JSON lazily from the detail wire shape with output and private ref omitted', async () => {
  const saved = detail();
  expect(saved.units[0]).not.toHaveProperty('output');
  expect(saved.units[0]).not.toHaveProperty('output_ref');
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue(saved), output: vi.fn().mockResolvedValue({ stored: true }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(api.output).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'View JSON u1' }));
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
  fireEvent.click(screen.getByRole('button', { name: 'View JSON u1' }));
  await act(async () => {});
  expect(api.output).not.toHaveBeenCalled();
  expect(screen.getAllByRole('heading', { name: /s1 · miti/ })[0].parentElement?.querySelector('pre')?.textContent).toBe(JSON.stringify(output));
});
it('refreshes terminal cancellation details before stopping polling', async () => {
  vi.useFakeTimers();
  const cancelled = { ...detail('cancelled'), completed_units: 4, cancelled_units: 2, units: [{ ...detail().units[0], unit_id: 'cancelled-unit', status: 'cancelled' as const }] };
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValueOnce(detail('running')).mockResolvedValue(cancelled), cancel: vi.fn().mockResolvedValue({ run_id: 'r1', status: 'cancelled' }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  await act(async () => {});
  expect(api.cancel).toHaveBeenCalledWith('r1');
  expect(api.run).toHaveBeenCalledTimes(2);
  expect(screen.getByText('cancelled · 4/4 units complete · 1 failed · 2 cancelled')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'View JSON u1' })).toBeNull();
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
  expect(screen.queryByRole('button', { name: 'View JSON u1' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }));
  await act(async () => {});
  expect(api.run).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.run).toHaveBeenCalledTimes(3);
  expect(screen.getByText('done · 4/4 units complete · 1 failed · 0 cancelled')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'View JSON u1' })).toBeTruthy();
  expect(screen.getByText(/~\$0.2500/)).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(9000); });
  expect(api.run).toHaveBeenCalledTimes(3);
});
it('history shows provenance and rerun preserves saved input with correct endpoint',async()=>{
 const api={...createEvalApi('',vi.fn()),runs:vi.fn().mockResolvedValue({runs:[summary()]}),options:vi.fn().mockResolvedValue({engines:[{id:'human',label:'Human',prod:false},{id:'miti',label:'MITI',prod:true}],models:[{id:'claude',label:'Claude',context_tokens:1,max_output_tokens:1,tiers:[{id:'claude-sonnet-5-5',efforts:['low'],default_effort:'low'}]}],defaults:{dataset:{engines:[],selection:{models:[],tiers:[],efforts:[]},label:''}}}),rerun:vi.fn().mockResolvedValue({run_id:'r2',status:'queued'}),dataset:vi.fn(),datasets:vi.fn()}; const onRerun=vi.fn(),onCreated=vi.fn(); const view=render(<History api={api} onOpen={vi.fn()} onRerun={onRerun}/>); expect(await screen.findByText('saved')).toBeTruthy(); expect(screen.getByText(/abc123/)).toBeTruthy(); expect(screen.getByText(/saved-model/)).toBeTruthy(); expect(screen.getByText(/STT excluded/)).toBeTruthy(); expect(screen.getByText(/1 unpriced unit/)).toBeTruthy(); fireEvent.click(screen.getByRole('button',{name:'Rerun with different engines/presets'})); expect(onRerun).toHaveBeenCalledWith(summary()); view.unmount(); render(<NewRun api={api} initialRun={summary()} onRunCreated={onCreated}/>); await act(async()=>{}); expect((screen.getByLabelText('Runs per cell') as HTMLSelectElement).value).toBe('3'); expect(screen.getByText(/older run chose models by preset/)).toBeTruthy(); expect((screen.getByLabelText('Human') as HTMLInputElement).disabled).toBe(false); fireEvent.click(screen.getByLabelText('Claude')); fireEvent.click(screen.getByLabelText('claude-sonnet-5-5')); fireEvent.click(screen.getByLabelText('low')); fireEvent.click(screen.getByRole('button',{name:'Start run'})); await act(async()=>{}); expect(api.rerun).toHaveBeenCalledWith('r1',{engines:['human','miti'],selection:{models:['claude'],tiers:['claude-sonnet-5-5'],efforts:['low']},repeats:3}); expect(api.dataset).not.toHaveBeenCalled(); expect(api.datasets).not.toHaveBeenCalled(); expect(onCreated).toHaveBeenCalledWith('r2');
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
it('shows Cancelling… and hides Cancel when the run summary says cancel_requested', async () => {
  vi.useFakeTimers();
  const api = { ...createEvalApi('', vi.fn()), run: vi.fn().mockResolvedValue({ ...detail('running'), cancel_requested: true }) };
  render(<RunView api={api} runId="r1" onRerun={vi.fn()} />);
  await act(async () => {});
  expect(screen.queryByRole('button', { name: 'Cancel run' })).toBeNull();
  expect((screen.getByRole('button', { name: 'Cancelling…' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/^cancelling · /)).toBeTruthy();
});
it('history loads more using the server cursor, retains rows on failure and retries that page', async () => {
  const runs = vi.fn().mockResolvedValueOnce({ runs: [summary()], next_cursor: 'page2' }).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ runs: [{ ...summary(), run_id: 'r2' }], next_cursor: null });
  render(<History api={{ ...createEvalApi('', vi.fn()), runs }} onOpen={vi.fn()} onRerun={vi.fn()} />);
  await screen.findByRole('button', { name: 'Open run r1' });
  fireEvent.click(screen.getByRole('button', { name: 'Load more' })); await screen.findByText('offline');
  expect(screen.getByRole('button', { name: 'Open run r1' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Retry history' })); await screen.findByRole('button', { name: 'Open run r2' });
  expect(runs.mock.calls[1][1]).toBe('page2'); expect(runs.mock.calls[2][1]).toBe('page2');
  expect(screen.getByRole('button', { name: 'Open run r1' })).toBeTruthy(); expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
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
  view.rerender(<History api={fresh} onOpen={vi.fn()} onRerun={vi.fn()} />); await screen.findByRole('button', { name: 'Open run fresh' });
  expect(old.runs.mock.calls[0][0].aborted).toBe(true);
  await act(async () => { resolve({ runs: [summary()], next_cursor: null }); }); expect(screen.queryByRole('button', { name: 'Open run r1' })).toBeNull();
});
it('history formats the run date for the locale instead of showing raw ISO', async () => {
  const api = { ...createEvalApi('', vi.fn()), runs: vi.fn().mockResolvedValue({ runs: [summary()] }) };
  render(<History api={api} onOpen={vi.fn()} onRerun={vi.fn()} />);
  expect(await screen.findByText(new Date('2026-11-23T10:00:00Z').toLocaleString())).toBeTruthy();
  expect(screen.queryByText('2026-11-23T10:00:00Z')).toBeNull();
});
it('renders — for unlabeled human values and shows quality label column only when present', () => {
 const partial = comparison(); partial.sessions[0].human = { ...partial.sessions[0].human!, giving_information: null, empathy: null };
 const view = render(<CompareView compare={partial} />);
 expect(screen.queryByText('Quality label')).toBeNull();
 const human = screen.getAllByRole('row')[1].querySelectorAll('td'); expect(human[ids.indexOf('giving_information')].textContent).toBe('—, n=0'); expect(human[ids.indexOf('empathy')].textContent).toBe('—, n=0');
 partial.sessions[0].quality_label = 'high'; view.rerender(<CompareView compare={partial} />);
 expect(screen.getByRole('columnheader', { name: 'Quality label' })).toBeTruthy(); expect(screen.getAllByText('high').length).toBeGreaterThan(0);
});
