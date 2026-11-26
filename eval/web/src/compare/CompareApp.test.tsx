// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, createEvalApi } from '../api';
import { CompareApp, comboLetter } from './CompareApp';
import overview from './fixtures/overview.json';
import deep from './fixtures/deepDive.json';
import analysis from './fixtures/analysis.json';
import { parseCompareUrl } from './compareUrl';
afterEach(cleanup);
const css=readFileSync(`${import.meta.dirname}/compare.css`,'utf8');
const state = (tab = 'overview') => parseCompareUrl(`?run=r1&view=compare&tab=${tab}`);
const api = () => ({...createEvalApi('',vi.fn()), run:vi.fn().mockRejectedValue(new Error('detail unavailable')), compareOverview:vi.fn().mockResolvedValue(overview), compareDeepDive:vi.fn().mockResolvedValue(deep), compareAnalysis:vi.fn().mockResolvedValue(analysis)});
it('renders overview header, cohorts and stable letters beyond Z',async()=>{
 const partial={...overview,header:{...overview.header,progress:{done_units:11,total_units:15,skipped_units:2}},coverage:{...overview.coverage,eval_status:'partial',runs_done:3,runs_total:8,runs_skipped:2,skipped_providers:[{provider:'gemini',after_failures:5}]},excluded:[{session_id:'s1',combo_key:null,reason:'cancelled'}]};
 const client={...api(),compareOverview:vi.fn().mockResolvedValue(partial)};
 render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 expect(screen.getByRole('status').textContent).toContain('Loading');
 await screen.findByRole('heading',{name:'Compare - Synthetic lines'});
 expect(screen.getByText('2 attempts each · 2 combos')).toBeTruthy();
 expect(screen.getByText('All 10 counts')).toBeTruthy();
 expect(screen.getByText('4 globals')).toBeTruthy();
 expect(screen.getByText(/Partial — 11 of 15 runs done, 2 skipped/)).toBeTruthy();
 expect(screen.getByText('3 of 8 runs done, 2 skipped')).toBeTruthy();
 expect(screen.getByText(/Gemini skipped after 5 failures in a row/)).toBeTruthy();
 expect(screen.getByText('s1: cancelled')).toBeTruthy();
 expect(screen.getByRole('link',{name:'Back to run'}).getAttribute('href')).toBe('?run=r1');
 expect(screen.getByText('20 of 20 complete')).toBeTruthy();
 expect([0,25,26,27,51,52].map(comboLetter)).toEqual(['A','Z','AA','AB','AZ','BA']);
});
it('navigates tabs by arrow key, caches completed tabs, and keeps tab errors local with Retry',async()=>{
 const client=api();client.compareDeepDive.mockRejectedValueOnce(new Error('deep failed')).mockResolvedValue(deep);
 const navigate=vi.fn(); const view=render(<CompareApp api={client} runId="r1" state={state()} navigate={navigate}/>);
 await screen.findByRole('heading',{name:'Compare - Synthetic lines'});
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
 const first=screen.getByRole('link',{name:'Combo A'}).getAttribute('href');
 view.rerender(<CompareApp api={client} runId="r1" state={{...state('deep'),combos:['first','second']}} navigate={navigate}/>);await act(async()=>{});
 expect(client.compareDeepDive).toHaveBeenCalledTimes(2);expect(screen.getByRole('link',{name:'Combo A'}).getAttribute('href')).toBe(first);
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
 expect(await screen.findByText('miti · Saved model / tier / effort',{selector:'.compare-legend-label'})).toBeTruthy();expect(client.run).toHaveBeenCalledTimes(1);
});
it('uses saved progress for the cancelled partial badge while retaining AI coverage',async()=>{
 const cancelled_at='2026-11-25T01:00:00Z';
 const partial={...overview,header:{...overview.header,progress:{done_units:11,total_units:15,skipped_units:2}},coverage:{...overview.coverage,eval_status:'partial',cancelled_at,runs_done:7,runs_total:10,runs_skipped:1}};
 const client={...api(),compareOverview:vi.fn().mockResolvedValue(partial)};
 const view=render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 await screen.findByRole('heading',{name:'Compare - Synthetic lines'});
 const badge=view.container.querySelector('[data-partial-badge]')!;
 expect(badge.textContent).toContain(`Partial — cancelled at ${new Date(cancelled_at).toLocaleString()}, 11 of 15 runs done, 2 skipped`);
 expect(screen.getByText('7 of 10 runs done, 1 skipped')).toBeTruthy();
});
it('rejects malformed nested tab payloads with local Retry and keeps other tabs usable',async()=>{
 const {default:lines}=await import('./fixtures/lines.json');let lineAttempts=0;
 const fetcher=vi.fn(async(input:RequestInfo|URL)=>{
  const path=new URL(String(input),'https://eval').pathname;
  if(path.endsWith('/overview'))return new Response(JSON.stringify(overview));
  if(path.endsWith('/analysis'))return new Response(JSON.stringify(analysis));
  if(path.endsWith('/lines'))return new Response(JSON.stringify(++lineAttempts===1?{...lines,globals:{}}:lines));
  if(path.endsWith('/reasoning'))return new Response(JSON.stringify({...lines,groups:[],next_cursor:null}));
  return new Response(JSON.stringify({detail:{code:'not_found'}}),{status:404});
 });
 const client=createEvalApi('https://eval',fetcher),navigate=vi.fn(),lineState={...state('lines'),session:'synthetic-s01'};
 const view=render(<CompareApp api={client} runId="r1" state={lineState} navigate={navigate}/>);
 expect((await screen.findByRole('alert')).textContent).toContain('invalid compare response');expect(screen.getByRole('button',{name:'Retry'})).toBeTruthy();
 view.rerender(<CompareApp api={client} runId="r1" state={state('more')} navigate={navigate}/>);await screen.findByRole('heading',{name:'More analysis'});expect(screen.queryByRole('alert')).toBeNull();
 view.rerender(<CompareApp api={client} runId="r1" state={lineState} navigate={navigate}/>);fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByRole('button',{name:'Inspect turn t5'});expect(screen.queryByRole('alert')).toBeNull();
 expect(fetcher.mock.calls.filter(([input])=>String(input).includes('/overview'))).toHaveLength(1);
});
it('renders the combo legend once above the tabs on every tab and uses a wrapping tablist',async()=>{
 const client=api();
 const view=render(<CompareApp api={client} runId="r1" state={state()} navigate={vi.fn()}/>);
 await screen.findByRole('heading',{name:'Compare - Synthetic lines'});
 expect(screen.getAllByRole('region',{name:'Combo legend'})).toHaveLength(1);
 const legend=screen.getByRole('region',{name:'Combo legend'}),tablist=screen.getByRole('tablist',{name:'Compare screens'});
 expect(legend.compareDocumentPosition(tablist)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 expect(within(tablist).getAllByRole('tab').map(tab=>tab.textContent)).toEqual(['Overview','Deep dive','More analysis','Line view']);
 view.rerender(<CompareApp api={client} runId="r1" state={state('deep')} navigate={vi.fn()}/>);await act(async()=>{});
 expect(screen.getAllByRole('region',{name:'Combo legend'})).toHaveLength(1);
 expect(screen.getByRole('tab',{name:'Deep dive'}).getAttribute('aria-selected')).toBe('true');
 expect(screen.getByRole('tab',{name:'Overview'}).getAttribute('aria-selected')).toBe('false');
 expect(screen.getByRole('tab',{name:'Deep dive'}).getAttribute('aria-controls')).toBe('compare-panel');
 expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe('compare-tab-deep');
});
it('flags a combo whose runs all failed in the legend',async()=>{
 const key=overview.combos[0].combo_key;
 const failed={...overview,excluded:[0,1].flatMap(repeat=>['synthetic-s01','synthetic-s02'].map(session_id=>({session_id,combo_key:key,repeat,reason:'failed:invalid_parameters'})))};
 render(<CompareApp api={{...api(),compareOverview:vi.fn().mockResolvedValue(failed)}} runId="r1" state={state()} navigate={vi.fn()}/>);
 await screen.findByRole('heading',{name:'Compare - Synthetic lines'});
 expect(within(screen.getByRole('region',{name:'Combo legend'})).getByText('failed: invalid_parameters')).toBeTruthy();
});
it('tabs never scroll horizontally: wrap with no overflow-x',()=>{
 const rule=css.match(/\[role="tablist"\]\s*\{([^}]*)\}/)![1];
 expect(rule).toMatch(/flex-wrap:\s*wrap/);
 expect(rule).not.toMatch(/overflow/);
});
