// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { CompareView, History, RunView } from './Runs';
import { NewRun } from './NewRun';
import { createEvalApi, type Compare, type RunDetail, type RunSummary } from './api';
afterEach(() => { cleanup(); vi.useRealTimers(); });
const ids = ['giving_information', 'persuade', 'persuade_with_permission', 'question', 'simple_reflection', 'complex_reflection', 'affirm', 'seeking_collaboration', 'emphasizing_autonomy', 'confront', 'cultivating_change_talk', 'softening_sustain_talk', 'partnership', 'empathy', 'reflection_question_ratio', 'pct_cr'];
const comparison = (human = true): Compare => ({ has_human: human, metrics: ids.map((id, i) => ({ id, label: id, group: i < 10 ? 'counts' : i < 14 ? 'globals' : 'summaries' })), sessions: [{ session_id: 's1', human: human ? Object.fromEntries(ids.map(id => [id, 2])) : null, cells: [{ engine: 'miti', preset: 'default', n: 2, failed: 1, unit_ids: ['u1', 'u2', 'u3'], values: Object.fromEntries(ids.map(id => [id, { mean: id === 'reflection_question_ratio' ? null : id === 'pct_cr' ? .75 : 2, min: 1, max: 3, n: id === 'reflection_question_ratio' ? 0 : 2 }])), ...(human ? { diff: { giving_information: 0 } } : {}) }] }], aggregates: human ? [{ engine: 'miti', preset: 'default', metrics: { n: 2, counts: { giving_information: { mae: 1, mean_bias: 0, n: 2 } }, globals: {}, summaries: {} } }] : [], notes: [] });
const summary = (): RunSummary => ({ run_id: 'r1', status: 'done', created_at: '2026-11-23T10:00:00Z', input: { dataset_id: 'saved', session_ids: ['s1'] }, engines: ['human', 'miti'], presets: ['default'], repeats: 3, total_units: 4, completed_units: 4, done_units: 3, failed_units: 1, cancelled_units: 0, usage: { input_tokens: 10, output_tokens: 4 }, cost_usd_est: .012, unpriced_units: 1, engine_versions: { miti: '1.2' }, engine_git_sha: { miti: 'abc123' }, resolved_presets: { default: { model: 'saved-model' } } });
const detail = (status: RunDetail['status'] = 'done'): RunDetail => ({ ...summary(), status, units: [{ unit_id: 'u1', session_id: 's1', engine: 'miti', preset: 'default', repeat: 0, status: 'done', stage: 'saved' }, { unit_id: 'u3', session_id: 's1', engine: 'miti', preset: 'default', repeat: 2, status: 'failed' }], compare: comparison() });
it('renders sixteen metrics, Human first, per-key n/range/nulls and server unit-weighted MAE', () => {
 render(<CompareView compare={comparison()} />);
 expect(screen.getAllByRole('columnheader').slice(0,3).map(e => e.textContent)).toEqual(['Metric','Human','miti · default']);
 expect(screen.getAllByRole('row')).toHaveLength(17);
 const row = screen.getByRole('row', { name: /giving_information/ }); expect(row.textContent).toContain('2 (1–3), n=2'); expect(row.textContent).toContain('1, n=2');
 expect(screen.getByText(/MAE over successful run units/)).toBeTruthy(); expect(screen.getByRole('row', {name: /reflection_question_ratio/}).textContent).toContain('—, n=0'); expect(screen.getByRole('row', {name: /pct_cr/}).textContent).toContain('75%'); expect(screen.getByText(/1 failed unit/)).toBeTruthy();
});
it('omits Human/error columns without reference and shows n=0 for pending Human', () => {
 const view = render(<CompareView compare={comparison(false)} />); expect(screen.queryByText('Human')).toBeNull(); expect(screen.queryByText(/MAE/)).toBeNull(); expect(screen.queryByText(/Diff vs Human/)).toBeNull();
 const pending = comparison(); pending.sessions[0].human = null; view.rerender(<CompareView compare={pending} />); expect(screen.getByRole('row', { name: /giving_information/ }).textContent).toContain('—, n=0');
});
it('selects sessions for signed differences', () => {
 const data = comparison(); data.sessions.push({...data.sessions[0], session_id:'s2', cells:[{...data.sessions[0].cells[0], diff:{giving_information:-3}}]}); render(<CompareView compare={data} />); fireEvent.change(screen.getByLabelText('Session'),{target:{value:'s2'}}); expect(screen.getByRole('row',{name:/giving_information/}).textContent).toContain('-3');
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
 const api={...createEvalApi('',vi.fn()),runs:vi.fn().mockResolvedValue({runs:[summary()]}),options:vi.fn().mockResolvedValue({engines:[{id:'human',label:'Human',prod:false},{id:'miti',label:'MITI',prod:true}],presets:[{name:'default',prod:true}],defaults:{dataset:{engines:[],presets:[]}}}),rerun:vi.fn().mockResolvedValue({run_id:'r2',status:'queued'}),dataset:vi.fn(),datasets:vi.fn()}; const onRerun=vi.fn(),onCreated=vi.fn(); const view=render(<History api={api} onOpen={vi.fn()} onRerun={onRerun}/>); expect(await screen.findByText('saved')).toBeTruthy(); expect(screen.getByText(/abc123/)).toBeTruthy(); expect(screen.getByText(/saved-model/)).toBeTruthy(); expect(screen.getByText(/STT excluded/)).toBeTruthy(); expect(screen.getByText(/1 unpriced unit/)).toBeTruthy(); fireEvent.click(screen.getByRole('button',{name:'Rerun with different engines/presets'})); expect(onRerun).toHaveBeenCalledWith(summary()); view.unmount(); render(<NewRun api={api} initialRun={summary()} onRunCreated={onCreated}/>); await act(async()=>{}); expect((screen.getByLabelText('Runs per cell') as HTMLSelectElement).value).toBe('3'); fireEvent.click(screen.getByLabelText('Human')); fireEvent.click(screen.getByRole('button',{name:'Start run'})); await act(async()=>{}); expect(api.rerun).toHaveBeenCalledWith('r1',{engines:['miti'],presets:['default'],repeats:3}); expect(api.dataset).not.toHaveBeenCalled(); expect(api.datasets).not.toHaveBeenCalled(); expect(onCreated).toHaveBeenCalledWith('r2');
});
it.each(['done', 'partial', 'failed', 'cancelled'] as const)('does not poll terminal %s runs', async status => {
 vi.useFakeTimers(); const api={...createEvalApi('',vi.fn()),run:vi.fn().mockResolvedValue(detail(status))}; render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); await act(async()=>{}); await act(async()=>{await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(1); expect(screen.queryByRole('button',{name:'Cancel run'})).toBeNull();
});
it('aborts in-flight progress requests on unmount and never schedules another poll', async()=>{
 vi.useFakeTimers(); let resolve!: (value:RunDetail)=>void; const api={...createEvalApi('',vi.fn()),run:vi.fn().mockImplementation(()=>new Promise<RunDetail>(r=>{resolve=r}))}; const view=render(<RunView api={api} runId="r1" onRerun={vi.fn()}/>); const signal=api.run.mock.calls[0][1] as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true); await act(async()=>{resolve(detail('running')); await vi.advanceTimersByTimeAsync(9000)}); expect(api.run).toHaveBeenCalledTimes(1);
});
