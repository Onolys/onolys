// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import { LineView } from './LineView';
import { CompareApp } from './CompareApp';
import type { CompareLines, CompareOverview, CompareTurn } from './compareApi';
import linesFixture from './fixtures/lines.json';
import overviewFixture from './fixtures/overview.json';
import turnFixture from './fixtures/turn.json';
afterEach(cleanup);
function props() {
 const data=structuredClone(linesFixture) as CompareLines, overview=structuredClone(overviewFixture) as CompareOverview;
 overview.header.line_sessions=[{session_id:'synthetic-s01',matched_lines:5},{session_id:'uploaded-real-id',matched_lines:8}];
 const popup=structuredClone(turnFixture) as CompareTurn;
 popup.turn_id='t5';popup.text='Saved text.\n  Spaces preserved.';popup.human={codes:['sr'],note:'Human note.'};
 popup.combos[data.combos[0].combo_key]={missing:null,codes:[['sr'],['cr'],['sr']],rationales:[{session_id:data.session_id,combo_key:data.combos[0].combo_key,repeat:1,rationale:'',withheld:true}],agree:{k:2,r:3}};
 const api={...createEvalApi('',vi.fn()),run:vi.fn().mockRejectedValue(new Error('unused')),compareOverview:vi.fn().mockResolvedValue(overview),compareLines:vi.fn().mockResolvedValue(data),compareTurn:vi.fn().mockResolvedValue(popup),compareLineMatches:vi.fn().mockResolvedValue({session_ids:['synthetic-s01']}),compareReasoning:vi.fn().mockResolvedValue({...linesFixture,groups:[{code:'empathy',snippets:[{session_id:data.session_id,combo_key:data.combos[0].combo_key,repeat:1,rationale:'Exact global reason.\nMore.',withheld:false,evidence:[{turn_id:'t3',quote:'Synthetic clinician turn 3.'}]}]}],next_cursor:null})};
 return {data,overview,api,runId:'r1',state:{view:'compare' as const,run:'r1',tab:'lines' as const,session:data.session_id},navigate:vi.fn(),legend:data.combos.map((combo,index)=>({combo,letter:String.fromCharCode(65+index),label:combo.combo_key}))};
}
it('preserves transcript, absent Human vs labelled none, missing lanes and scoped globals',async()=>{
 const p=props();p.data.lanes.human!.t3=[];const view=render(<LineView {...p}/>);
 expect(view.container.querySelector('[data-turn="t2"] [data-human]')?.textContent).toBe('');expect(view.container.querySelector('[data-turn="t3"] [data-human]')?.textContent).toBe('none');
 expect(view.container.querySelector('[data-turn="t5"] [data-transcript]')?.textContent).toBe(p.data.turns[3].text);expect(screen.getAllByText('no line-level output').length).toBeGreaterThan(0);
 expect(await screen.findByText(/Exact global reason/)).toHaveProperty('textContent','Exact global reason.\nMore.');
 expect(p.api.compareReasoning).toHaveBeenCalledWith('r1',{session:'synthetic-s01',kind:'global',combos:p.data.combos.map(c=>c.combo_key)},expect.any(AbortSignal));expect(p.api.compareTurn).not.toHaveBeenCalled();
 expect(screen.getByRole('option',{name:'uploaded-real-id · 8 matched lines'})).toBeTruthy();
});
it('opens URL popup, preserves rationale and repeats, Escape restores focus',async()=>{
 const p=props();const view=render(<LineView {...p}/>);const trigger=screen.getByRole('button',{name:'Inspect turn t5'});trigger.focus();fireEvent.click(trigger);expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({turn:'t5'}));
 view.rerender(<LineView {...p} state={{...p.state,turn:'t5'}}/>);const dialog=await screen.findByRole('dialog');await within(dialog).findByText('withheld');
 expect(within(dialog).getByText(/Saved text/)).toHaveProperty('textContent','Saved text.\n  Spaces preserved.');expect(within(dialog).getByText('2 of 3 repeats agree')).toBeTruthy();expect(within(dialog).getByText('Human note.')).toBeTruthy();
 fireEvent.keyDown(dialog,{key:'Escape'});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({turn:undefined}));view.rerender(<LineView {...p}/>);await waitFor(()=>expect(document.activeElement).toBe(trigger));
});
it('collapses six lanes with expandable agreement',()=>{
 const p=props(),first=p.data.combos[0],lane=p.data.lanes[first.combo_key];p.data.combos=Array.from({length:6},(_,i)=>({...first,combo_key:`c${i}`}));p.legend=p.data.combos.map((combo,i)=>({combo,letter:String.fromCharCode(65+i),label:combo.combo_key}));for(const combo of p.data.combos)p.data.lanes[combo.combo_key]=structuredClone(lane);
 const view=render(<LineView {...p}/>), row=view.container.querySelector('[data-turn="t3"]') as HTMLElement;fireEvent.click(within(row).getByRole('button',{name:'+6 agree'}));expect(within(row).getByText('F: question / question')).toBeTruthy();
});
it('keeps human none/multi, prediction and disagreement filters in URL',()=>{
 const p=props();render(<LineView {...p}/>);fireEvent.change(screen.getByLabelText('Human code'),{target:{value:'multi'}});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({code:'multi',turn:undefined}));fireEvent.change(screen.getByLabelText('Prediction code'),{target:{value:'none'}});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({metric:'none'}));fireEvent.click(screen.getByLabelText('Only disagreements'));expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({only:'disagree'}));
});
it.each(['human','both'])('replaces unavailable %s labels',missing=>{const p=props();p.data.missing=missing;render(<LineView {...p}/>);expect(screen.getByText('no line-level output (human)')).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t5'})).toBeNull();});
it('defaults to most matched real uploaded session and resolves direct filtered links once',async()=>{
 const p=props();const view=render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines'}} navigate={p.navigate}/>);await screen.findByRole('button',{name:'Inspect turn t5'});expect(p.api.compareLines).toHaveBeenCalledWith('r1','uploaded-real-id',expect.any(Object),expect.any(AbortSignal));
 view.rerender(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',code:'sr',metric:'cr',combo:p.data.combos[0].combo_key}} navigate={p.navigate}/>);await act(async()=>{});expect(p.api.compareLineMatches).toHaveBeenCalledTimes(1);expect(p.api.compareLines).toHaveBeenLastCalledWith('r1','synthetic-s01',expect.any(Object),expect.any(AbortSignal));
});
it('paginates global reasons once per page, preserves old pages and isolates a retry',async()=>{
 const p=props(),payload=await p.api.compareReasoning();p.api.compareReasoning.mockReset().mockRejectedValueOnce(new Error('Global reasons unavailable')).mockResolvedValueOnce({...payload,next_cursor:'page2'}).mockResolvedValueOnce({...payload,groups:[{code:'empathy',snippets:[{...payload.groups[0].snippets[0],rationale:'Second page'}]}]});
 render(<LineView {...p}/>);expect(await screen.findByText('Global reasons unavailable')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText(/Exact global reason/);fireEvent.click(screen.getByRole('button',{name:'Load more global reasons'}));await screen.findByText('Second page');expect(screen.getByText(/Exact global reason/)).toBeTruthy();expect(p.api.compareReasoning).toHaveBeenLastCalledWith('r1',expect.objectContaining({session:'synthetic-s01',kind:'global',cursor:'page2'}),expect.any(AbortSignal));expect(p.api.compareTurn).not.toHaveBeenCalled();
});
it('filters none and multi against explicit Human labels and selected prediction repeats',()=>{
 const p=props();p.data.lanes.human!.t3=[];
 const view=render(<LineView {...p} state={{...p.state,code:'none'}}/>);expect(screen.getByRole('button',{name:'Inspect turn t3'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t2'})).toBeNull();
 view.rerender(<LineView {...p} state={{...p.state,code:'multi',metric:'multi',combo:p.data.combos[0].combo_key}}/>);expect(screen.getByRole('button',{name:'Inspect turn t7'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t3'})).toBeNull();
 view.rerender(<LineView {...p} state={{...p.state,code:'sr',metric:'cr',combo:p.data.combos[0].combo_key,only:'disagree'}}/>);expect(screen.getByRole('button',{name:'Inspect turn t5'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t7'})).toBeNull();
});
it('aborts global and popup requests when scope changes and shows the transcript conflict locally',async()=>{
 const p=props();const {ApiError}=await import('../api');p.api.compareTurn.mockRejectedValueOnce(new ApiError('changed',409,'transcript_changed'));
 const view=render(<LineView {...p} state={{...p.state,turn:'t5'}}/>);expect(await screen.findByText('The saved transcript changed since this run; lines cannot be shown.')).toBeTruthy();expect(screen.getByRole('heading',{name:'Line view',hidden:true})).toBeTruthy();
 const turnSignal=p.api.compareTurn.mock.calls[0][4] as AbortSignal,reasonSignal=p.api.compareReasoning.mock.calls[0][2] as AbortSignal;view.unmount();expect(turnSignal.aborted).toBe(true);expect(reasonSignal.aborted).toBe(true);
});
it('shows no human reference with no global request',()=>{
 const p=props();p.data.has_human=false;render(<LineView {...p}/>);expect(screen.getByText('no human reference')).toBeTruthy();expect(p.api.compareReasoning).not.toHaveBeenCalled();
});
it('preserves nonempty popup rationale and verified quote verbatim',async()=>{
 const p=props(),popup=await p.api.compareTurn(),key=p.data.combos[0].combo_key;
 popup.combos[key].rationales=[{session_id:p.data.session_id,combo_key:key,repeat:2,rationale:'Exact reason.\n  whitespace.',withheld:false,quote:'Saved text.',quote_verified:true}];p.api.compareTurn.mockResolvedValue(popup);
 render(<LineView {...p} state={{...p.state,turn:'t5'}}/>);expect(await screen.findByText(/Exact reason/)).toHaveProperty('textContent','Exact reason.\n  whitespace.');expect(screen.getByText('Saved text.',{selector:'blockquote'})).toBeTruthy();
});
it('handles direct matching-session errors with Retry and empty results without per-session fetches',async()=>{
 const p=props();p.api.compareLineMatches.mockRejectedValueOnce(new Error('Matching sessions unavailable')).mockResolvedValueOnce({session_ids:[]});
 render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',code:'none',metric:'multi',combo:p.data.combos[0].combo_key}} navigate={p.navigate}/>);
 expect(await screen.findByText('Matching sessions unavailable')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Retry'}));await screen.findByText('No matching sessions');expect(p.api.compareLines).not.toHaveBeenCalled();expect(p.api.compareLineMatches).toHaveBeenCalledTimes(2);
});
