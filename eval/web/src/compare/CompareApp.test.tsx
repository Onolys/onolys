// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, createEvalApi } from '../api';
import { CompareApp, comboLetter } from './CompareApp';
import overview from './fixtures/overview.json';
import deep from './fixtures/deepDive.json';
import analysis from './fixtures/analysis.json';
import { parseCompareUrl } from './compareUrl';
afterEach(cleanup);
const state = (tab = 'overview') => parseCompareUrl(`?run=r1&view=compare&tab=${tab}`);
const api = () => ({...createEvalApi('',vi.fn()), run:vi.fn().mockRejectedValue(new Error('detail unavailable')), compareOverview:vi.fn().mockResolvedValue(overview), compareDeepDive:vi.fn().mockResolvedValue(deep), compareAnalysis:vi.fn().mockResolvedValue(analysis)});
it('renders overview header, cohorts and stable letters beyond Z',async()=>{
 const partial={...overview,coverage:{...overview.coverage,eval_status:'partial',runs_done:3,runs_total:8,runs_skipped:2,skipped_providers:[{provider:'gemini',after_failures:5}]},excluded:[{session_id:'s1',combo_key:null,reason:'cancelled'}]};
 const client={...api(),compareOverview:vi.fn().mockResolvedValue(partial)};
 render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 expect(screen.getByRole('status').textContent).toContain('Loading');
 await screen.findByRole('heading',{name:'Synthetic lines'});
 expect(screen.getByText('2 sessions, 2 repeats')).toBeTruthy();
 expect(screen.getByText('Human labels: all counts, 4 globals')).toBeTruthy();
 expect(screen.getByText(/Partial — 3 of 8 runs done, 2 skipped/)).toBeTruthy();
 expect(screen.getByText(/Gemini skipped after 5 failures in a row/)).toBeTruthy();
 expect(screen.getByText(/s1.*cancelled/)).toBeTruthy();
 expect(screen.getByRole('link',{name:'Back to run'}).getAttribute('href')).toBe('?run=r1');
 expect(screen.getByText('gi: paired 2 of 2')).toBeTruthy();
 expect([0,25,26,27,51,52].map(comboLetter)).toEqual(['A','Z','AA','AB','AZ','BA']);
});
it('navigates tabs by arrow key, caches completed tabs, and keeps tab errors local with Retry',async()=>{
 const client=api();client.compareDeepDive.mockRejectedValueOnce(new Error('deep failed')).mockResolvedValue(deep);
 const navigate=vi.fn(); const view=render(<CompareApp api={client} runId="r1" state={state()} navigate={navigate}/>);
 await screen.findByRole('heading',{name:'Synthetic lines'});
 fireEvent.keyDown(screen.getByRole('tab',{name:'Overview'}),{key:'ArrowRight'});
 expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({tab:'deep'}));
 view.rerender(<CompareApp api={client} runId="r1" state={state('deep')} navigate={navigate}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('deep failed');
 fireEvent.click(screen.getByRole('button',{name:'Retry'})); await act(async()=>{});
 expect(screen.queryByRole('alert')).toBeNull(); expect(client.compareDeepDive).toHaveBeenCalledTimes(2);
 view.rerender(<CompareApp api={client} runId="r1" state={state('more')} navigate={navigate}/>);await act(async()=>{});
 view.rerender(<CompareApp api={client} runId="r1" state={state('deep')} navigate={navigate}/>);await act(async()=>{});
 expect(client.compareDeepDive).toHaveBeenCalledTimes(2);expect(client.compareOverview).toHaveBeenCalledTimes(1);expect(client.run).toHaveBeenCalledTimes(1);
});
it.each([[404,'not_found','Run not found'],[409,'no_completed_runs','No completed runs to compare yet'],[409,'not_finished','No completed runs to compare yet']])('shows HTTP %s %s despite detail failure',async(status,code,text)=>{
 const client={...api(),compareOverview:vi.fn().mockRejectedValue(new ApiError('server',Number(status),String(code)))};
 render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 expect(await screen.findByText(text)).toBeTruthy(); expect(screen.getByRole('link',{name:status===404?'History':'Back to run'})).toBeTruthy();
});
it('refetches a new combo cohort, reuses its cache, and preserves overview legend order',async()=>{
 const client=api(); const navigate=vi.fn();
 const view=render(<CompareApp api={client} runId="r1" state={{...state('deep'),combos:['second']}} navigate={navigate}/>);await act(async()=>{});
 expect(client.compareDeepDive).toHaveBeenLastCalledWith('r1',{combos:['second'],code:undefined,combo:undefined},expect.any(AbortSignal));
 const first=screen.getByRole('link',{name:'A'}).getAttribute('href');
 view.rerender(<CompareApp api={client} runId="r1" state={{...state('deep'),combos:['first','second']}} navigate={navigate}/>);await act(async()=>{});
 expect(client.compareDeepDive).toHaveBeenCalledTimes(2);expect(screen.getByRole('link',{name:'A'}).getAttribute('href')).toBe(first);
 view.rerender(<CompareApp api={client} runId="r1" state={{...state('deep'),combos:['second']}} navigate={navigate}/>);await act(async()=>{});
 expect(client.compareDeepDive).toHaveBeenCalledTimes(2);
});
it('handles a tab-local transcript conflict and aborts in-flight requests on unmount',async()=>{
 const client={...api(),compareLines:vi.fn().mockRejectedValue(new ApiError('conflict',409,'transcript_changed'))};
 const view=render(<CompareApp api={client} runId="r1" state={{...state('lines'),session:'s1'}} navigate={vi.fn()}/>);
 expect(await screen.findByText('The saved transcript changed since this run; lines cannot be shown.')).toBeTruthy();
 view.unmount();expect((client.compareLines.mock.calls[0] as unknown as [string,string,unknown,AbortSignal])[3].aborted).toBe(true);
 expect((client.compareOverview.mock.calls[0] as unknown as [string,unknown,AbortSignal])[2].aborted).toBe(true);
});
it('retries an overview failure and keeps exact saved combo labels with distinct engines',async()=>{
 const client={...api(),run:vi.fn().mockResolvedValue({input:{dataset_id:'saved',session_ids:['s1']},combo_labels:{[overview.combos[0].combo_key]:'Saved model / tier / effort'}})};
 client.compareOverview.mockRejectedValueOnce(new Error('temporary'));
 render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('temporary');
 fireEvent.click(screen.getByRole('button',{name:'Retry'}));
 expect(await screen.findByText('miti · Saved model / tier / effort')).toBeTruthy();expect(client.run).toHaveBeenCalledTimes(1);
});
