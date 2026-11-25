// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import { DeepDive } from './DeepDive';
import { CompareApp } from './CompareApp';
import type { CompareDeepDive, CompareOverview } from './compareApi';
import { parseCompareUrl } from './compareUrl';
import overviewFixture from './fixtures/overview.json';
import deepFixture from './fixtures/deepDive.json';
import reasoning from './fixtures/reasoning.json';
afterEach(cleanup);
const deep = () => structuredClone(deepFixture) as CompareDeepDive;
const overview = () => structuredClone(overviewFixture) as CompareOverview;
const state = parseCompareUrl('?run=r1&view=compare&tab=deep');
const client = () => ({...createEvalApi('',vi.fn()),run:vi.fn().mockRejectedValue(new Error('unused')),compareOverview:vi.fn().mockResolvedValue(overview()),compareDeepDive:vi.fn().mockResolvedValue(deep()),compareReasoning:vi.fn().mockResolvedValue(reasoning),compareLineMatches:vi.fn().mockResolvedValue({session_ids:['synthetic-s01','synthetic-s02']})});
function props(data=deep()) {return {data,overview:overview(),state,runId:'r1',navigate:vi.fn(),api:client(),legend:overview().combos.map((combo,index)=>({combo,letter:String.fromCharCode(65+index),label:combo.combo_key}))};}
it('renders server values, same-cohort human means, n/of, bias words, dots and table twins',()=>{
 const data=deep();data.counts.human={gi:{value:7.25,min:7,max:8,n:1,na:null}};
 const p=props(data); const view=render(<DeepDive {...p}/>);
 expect(screen.getByRole('checkbox',{name:'Human (fixed)'})).toHaveProperty('disabled',true);
 expect(screen.getAllByText('under-counts by 50%')[0]).toBeTruthy();
 expect(screen.getAllByText(/n\/a - human count is zero/).length).toBeGreaterThan(0);
 expect(view.container.querySelector('[data-human-count="gi"]')?.textContent).toContain('7.25');
 expect(view.container.querySelectorAll('[data-global-dot]').length).toBe(40);
 expect(screen.getAllByText(/paired 2 of 2/).length).toBeGreaterThan(0);
 expect(screen.getAllByText(/How to read:/).length).toBeGreaterThan(5);
 expect(screen.getAllByRole('table',{name:'Line agreement'})[0].textContent).toContain('Precision');
 expect(screen.getByText('10 of 10 codes labeled')).toBeTruthy();expect(p.api.compareReasoning).not.toHaveBeenCalled();
});
it.each([['human','no line-level output (human)'],['both','no line-level output (both)']])('hides line charts for %s missing output',(missing,text)=>{
 const data=deep();data.lines.missing=missing;render(<DeepDive {...props(data)}/>);
 expect(screen.getByText(text)).toBeTruthy();expect(screen.queryByRole('table',{name:'Line agreement'})).toBeNull();expect(screen.queryByLabelText('Confusion combo')).toBeNull();
});
it('names a missing combo and switches the confusion matrix without losing multi',()=>{
 const data=deep(), key=data.combos[0].combo_key;data.lines.combos[key].lane='no line-level output';data.lines.combos[data.combos[1].combo_key].lane=null;
 const view=render(<DeepDive {...props(data)}/>);expect(screen.getByText('no line-level output (A)')).toBeTruthy();
 expect(screen.getByLabelText('Confusion combo')).toHaveProperty('value',data.combos[1].combo_key);expect(view.container.querySelector('[data-confusion-multi]')).toBeTruthy();
});
it('keeps confusion totals plus multi equal aligned lines and resolves matching sessions in one request',async()=>{
 const p=props(), key=p.data.combos[0].combo_key;const view=render(<DeepDive {...p}/>);
 expect(Array.from(view.container.querySelectorAll('[data-confusion-value]')).reduce((sum,node)=>sum+Number(node.getAttribute('data-confusion-value')),0)).toBe(p.data.lines.combos[key].aligned);
 const button=screen.getAllByRole('button',{name:/Human question, A question:/})[0];fireEvent.click(button);
 expect(await screen.findByRole('link',{name:'synthetic-s01'})).toBeTruthy();
 expect(p.api.compareLineMatches).toHaveBeenCalledWith('r1',expect.objectContaining({combo:key,code:'question',metric:'question',combos:p.data.combos.map(c=>c.combo_key)}),expect.any(AbortSignal));
 expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({tab:'lines',session:'synthetic-s01',only:'disagree',combo:key,code:'question',metric:'question'}));
});
it('loads reasoning on demand, preserves verbatim and withheld text and follows cursors',async()=>{
 const p=props();const group=reasoning.groups.find(group=>group.code==='question')!;
 p.api.compareReasoning.mockResolvedValueOnce({...reasoning,groups:[{...group,snippets:group.snippets.slice(0,1)}],next_cursor:'page2'}).mockResolvedValueOnce({...reasoning,groups:[{...group,snippets:group.snippets.slice(1,2)}],next_cursor:null});
 render(<DeepDive {...p}/>);fireEvent.click(screen.getByRole('button',{name:'Load reasoning question A'}));
 expect(await screen.findByText('withheld')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Load more'}));expect(await screen.findByText(group.snippets[1].rationale)).toBeTruthy();
 expect(p.api.compareReasoning).toHaveBeenLastCalledWith('r1',expect.objectContaining({code:'question',combo:p.data.combos[0].combo_key,cursor:'page2'}),expect.any(AbortSignal));
});
it('defaults to three available Count errors, refetches picker changes and caches effective subsets',async()=>{
 const ov=overview();const original=ov.combos[0];ov.combos=Array.from({length:5},(_,i)=>({...original,combo_key:`c${i}`}));
 const cell=Object.values(ov.count_error)[0];ov.count_error=Object.fromEntries(ov.combos.map((combo,i)=>[combo.combo_key,{...cell,off:[9,1,2,3,0][i],na:i===4?{reason:'unavailable'}:null}]));
 const api={...client(),compareOverview:vi.fn().mockResolvedValue(ov)};const navigate=vi.fn();
 const view=render(<CompareApp api={api} runId="r1" state={state} navigate={navigate}/>);await act(async()=>{});
 expect(api.compareDeepDive).toHaveBeenLastCalledWith('r1',expect.objectContaining({combos:['c1','c2','c3']}),expect.any(AbortSignal));
 fireEvent.click(screen.getByRole('checkbox',{name:/A ·/}));expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({combos:['c1','c2','c3','c0']}));
 view.rerender(<CompareApp api={api} runId="r1" state={{...state,combos:['c1','c2','c3','c0']}} navigate={navigate}/>);await act(async()=>{});expect(api.compareDeepDive).toHaveBeenCalledTimes(2);
 view.rerender(<CompareApp api={api} runId="r1" state={{...state,combos:['c1','c2','c3']}} navigate={navigate}/>);await act(async()=>{});expect(api.compareDeepDive).toHaveBeenCalledTimes(2);
 expect(screen.getByRole('link',{name:'A'}).getAttribute('href')).toContain('combos=c0');
});

it('loads Human gold notes without a combo filter and retains verbatim notes over pages',async()=>{
 const p=props();
 const note={session_id:'synthetic-s01',turn_id:'t7',note:'Saved human note.\nSecond line.'};
 p.api.compareReasoning.mockResolvedValueOnce({...reasoning,groups:[{code:'affirm',snippets:[],human_notes:[note]}],next_cursor:'notes2'}).mockResolvedValueOnce({...reasoning,groups:[{code:'affirm',snippets:[],human_notes:[{...note,turn_id:'t9',note:'Another saved note'}]}],next_cursor:null});
 render(<DeepDive {...p}/>);fireEvent.click(screen.getByRole('button',{name:'Load human notes affirm'}));
 expect((await screen.findByText(/Saved human note/)).textContent).toBe(note.note);
 expect(p.api.compareReasoning).toHaveBeenLastCalledWith('r1',expect.objectContaining({code:'affirm',combo:undefined}),expect.any(AbortSignal));
 fireEvent.click(screen.getByRole('button',{name:'Load more'}));await screen.findByText('Another saved note');expect(screen.getByText(/Saved human note/).textContent).toBe(note.note);
});
it('shows no human reference and no charts for unlabelled runs',()=>{
 const data=deep();data.has_human=false;render(<DeepDive {...props(data)}/>);
 expect(screen.getByText('no human reference')).toBeTruthy();expect(screen.queryByRole('img')).toBeNull();
});
it('retains an explicit selection even if its Count error is unavailable and renders its requested cohorts',async()=>{
 const ov=overview(), key=ov.combos[1].combo_key;ov.count_error[key].na={reason:'unavailable'};
 const d=deep();d.cohorts={gi:{paired:1,of:7}};
 const api={...client(),compareOverview:vi.fn().mockResolvedValue(ov),compareDeepDive:vi.fn().mockResolvedValue(d)};
 render(<CompareApp api={api} runId="r1" state={{...state,combos:[key]}} navigate={vi.fn()}/>);await screen.findByText('gi: paired 1 of 7');
 expect(api.compareDeepDive).toHaveBeenLastCalledWith('r1',expect.objectContaining({combos:[key]}),expect.any(AbortSignal));
});
it('reports empty matching sessions and supports retry after a matching-session failure',async()=>{
 const p=props();p.api.compareLineMatches.mockRejectedValueOnce(new Error('Match lookup failed')).mockResolvedValueOnce({session_ids:[]});
 render(<DeepDive {...p}/>);fireEvent.click(screen.getByRole('button',{name:/Human sr, A cr:/}));
 expect(await screen.findByText('Match lookup failed')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Retry matching sessions'}));
 expect(await screen.findByText('No matching sessions')).toBeTruthy();expect(p.navigate).not.toHaveBeenCalled();
});

it('switches displayed confusion data and links the multi bucket with exact filters',async()=>{
 const p=props(),second=p.data.combos[1].combo_key;
 p.data.lines.combos[second]={...structuredClone(p.data.lines.combos[p.data.combos[0].combo_key]),confusion:{none:{none:2}},multi:3,aligned:5};
 const view=render(<DeepDive {...p}/>);fireEvent.change(screen.getByLabelText('Confusion combo'),{target:{value:second}});
 expect(screen.getByRole('button',{name:'Human none, B none: 2'})).toBeTruthy();expect(screen.queryByRole('button',{name:/Human sr, A cr/})).toBeNull();
 const multi=view.container.querySelector('[data-confusion-multi]')!;fireEvent.click(multi);
 await act(async()=>{});expect(p.api.compareLineMatches).toHaveBeenLastCalledWith('r1',expect.objectContaining({combo:second,code:'multi',metric:'multi'}),expect.any(AbortSignal));
});
