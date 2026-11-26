// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
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
const cssFile='lineView.css'; // variable so Vite does not rewrite new URL() into an asset URL
const lineCss=readFileSync(new URL(cssFile,import.meta.url),'utf8');
const openRatings=()=>fireEvent.click(screen.getByRole('button',{name:'Show global ratings'}));
const openReasoning=async()=>fireEvent.click(await screen.findByRole('button',{name:'Show reasoning'}));
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
 openRatings();await openReasoning();expect(await screen.findByText(/Exact global reason/)).toHaveProperty('textContent','Exact global reason.\nMore.');
 expect(p.api.compareReasoning).toHaveBeenCalledWith('r1',{session:'synthetic-s01',kind:'global',combos:p.data.combos.map(c=>c.combo_key)},expect.any(AbortSignal));expect(p.api.compareTurn).not.toHaveBeenCalled();
 expect(screen.getByRole('option',{name:'uploaded-real-id · 8 matched lines'})).toBeTruthy();
});
it('opens URL popup, preserves rationale and repeats, Escape restores focus',async()=>{
 const p=props();const view=render(<LineView {...p}/>);const trigger=screen.getByRole('button',{name:'Inspect turn t5'});trigger.focus();fireEvent.click(trigger);expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({turn:'t5'}));
 view.rerender(<LineView {...p} state={{...p.state,turn:'t5'}}/>);const dialog=await screen.findByRole('dialog');await within(dialog).findByText('withheld');
 expect(within(dialog).getByText(/Saved text/)).toHaveProperty('textContent','Saved text.\n  Spaces preserved.');expect(within(dialog).getByText('2 of 3 repeats agree')).toBeTruthy();expect(within(dialog).getByText('Human note.')).toBeTruthy();
 fireEvent.keyDown(dialog,{key:'Escape'});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({turn:undefined}));view.rerender(<LineView {...p}/>);await waitFor(()=>expect(document.activeElement).toBe(trigger));
});
it('caps lanes at three combo columns with ComboTag headers; the combo filter picks extras',()=>{
 const p=props(),first=p.data.combos[0],lane=p.data.lanes[first.combo_key];p.data.combos=Array.from({length:6},(_,i)=>({...first,combo_key:`c${i}`}));p.legend=p.data.combos.map((combo,i)=>({combo,letter:String.fromCharCode(65+i),label:combo.combo_key}));for(const combo of p.data.combos)p.data.lanes[combo.combo_key]=structuredClone(lane);
 const view=render(<LineView {...p}/>);const heads=[...view.container.querySelectorAll('thead th')].slice(4);
 expect(heads.map(h=>h.getAttribute('aria-label')??h.querySelector('[role=img]')?.getAttribute('aria-label'))).toEqual(['Combo A','Combo B','Combo C']);
 const row=view.container.querySelector('[data-turn="t3"]') as HTMLElement;expect(row.querySelectorAll('td[data-label^="Combo "]')).toHaveLength(3);expect(within(row).queryByRole('button',{name:/agree/})).toBeNull();
 const boxes=within(screen.getByRole('group',{name:/Combo lanes/})).getAllByRole('checkbox') as HTMLInputElement[];
 expect(boxes.filter(b=>b.checked)).toHaveLength(3);expect(boxes.filter(b=>!b.checked).every(b=>b.disabled)).toBe(true);
 fireEvent.click(boxes[0]);expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({combos:['c1','c2']}));
});
it('uses legend index for ComboTag in headers, popup and ratings when selection order differs from the legend',async()=>{
 const p=props(),[a,b]=p.data.combos.map(c=>c.combo_key);const popup=await p.api.compareTurn();popup.combos[b]={missing:null,codes:[['sr']],rationales:[],agree:{k:1,r:1}};
 const state={...p.state,combos:[b,a],turn:'t5'};const view=render(<LineView {...p} state={state}/>);
 const shapeOf=(el:Element)=>el.querySelector('svg')?.getAttribute('data-shape');const colourOf=(el:Element)=>(el as HTMLElement).style.color;
 const ref=(letter:string)=>{const t=view.container.querySelector('.line-view thead [aria-label="Combo '+letter+'"]') as Element;return {shape:shapeOf(t),color:colourOf(t)};};
 const {shape:shapeA,color:colorA}=ref('A'),{shape:shapeB,color:colorB}=ref('B');expect(shapeA).not.toBe(shapeB);expect(colorA).not.toBe(colorB);
 const heads=[...view.container.querySelectorAll('thead [role=img]')];expect(heads.map(h=>h.getAttribute('aria-label'))).toEqual(['Combo B','Combo A']);
 const dialog=await screen.findByRole('dialog');await within(dialog).findByText('1 of 1 repeats agree');
 const inDialogB=within(dialog).getByRole('img',{name:'Combo B'}),inDialogA=within(dialog).getByRole('img',{name:'Combo A'});
 expect(shapeOf(inDialogB)).toBe(shapeB);expect(colourOf(inDialogB)).toBe(colorB);expect(shapeOf(inDialogA)).toBe(shapeA);expect(colourOf(inDialogA)).toBe(colorA);
 fireEvent.click(screen.getByRole('button',{name:'Show global ratings',hidden:true}));const table=await screen.findByRole('table',{name:'Session global ratings',hidden:true});
 for(const [letter,shape,color] of [['A',shapeA,colorA],['B',shapeB,colorB]] as const){const tags=within(table).queryAllByRole('img',{name:'Combo '+letter,hidden:true});for(const tag of tags){expect(shapeOf(tag)).toBe(shape);expect(colourOf(tag)).toBe(color);}}
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
 render(<LineView {...p}/>);openRatings();expect(await screen.findByText('Global reasons unavailable')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Retry'}));await openReasoning();await screen.findByText(/Exact global reason/);fireEvent.click(screen.getByRole('button',{name:'Load more global reasons'}));await screen.findByText('Second page');expect(screen.getByText(/Exact global reason/)).toBeTruthy();expect(p.api.compareReasoning).toHaveBeenLastCalledWith('r1',expect.objectContaining({session:'synthetic-s01',kind:'global',cursor:'page2'}),expect.any(AbortSignal));expect(p.api.compareTurn).not.toHaveBeenCalled();
});
it('filters none and multi against explicit Human labels and selected prediction repeats',()=>{
 const p=props();p.data.lanes.human!.t3=[];
 const view=render(<LineView {...p} state={{...p.state,code:'none'}}/>);expect(screen.getByRole('button',{name:'Inspect turn t3'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t2'})).toBeNull();
 view.rerender(<LineView {...p} state={{...p.state,code:'multi',metric:'multi',combo:p.data.combos[0].combo_key}}/>);expect(screen.getByRole('button',{name:'Inspect turn t7'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t3'})).toBeNull();
 view.rerender(<LineView {...p} state={{...p.state,code:'sr',metric:'cr',combo:p.data.combos[0].combo_key,only:'disagree'}}/>);expect(screen.getByRole('button',{name:'Inspect turn t5'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Inspect turn t7'})).toBeNull();
});
it('aborts global and popup requests when scope changes and shows the transcript conflict locally',async()=>{
 const p=props();const {ApiError}=await import('../api');p.api.compareTurn.mockRejectedValueOnce(new ApiError('changed',409,'transcript_changed'));
 const view=render(<LineView {...p} state={{...p.state,turn:'t5'}}/>);fireEvent.click(screen.getByRole('button',{name:'Show global ratings',hidden:true}));expect(await screen.findByText('The saved transcript changed since this run; lines cannot be shown.')).toBeTruthy();expect(screen.getByRole('heading',{name:'Line view',hidden:true})).toBeTruthy();
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
it('keeps skipped, failed and empty turn lanes out of agreement ',()=>{
 const p=props(),first=p.data.combos[0];p.data.combos=Array.from({length:3},(_,i)=>({...first,combo_key:`c${i}`}));p.legend=p.data.combos.map((combo,i)=>({combo,letter:String.fromCharCode(65+i),label:combo.combo_key}));p.data.lanes.human!.t3=[];
 for(const combo of p.data.combos)p.data.lanes[combo.combo_key]={missing:null,n:1,repeats:1,turns:{t3:[[]]}};
 p.data.lanes.c0={missing:null,n:0,repeats:0,turns:{t3:[]}};p.data.lanes.c1={missing:null,n:0,repeats:0,turns:{}};p.data.lanes.c2={missing:null,n:1,repeats:1,turns:{t3:[]}};
 p.data.excluded=[{session_id:p.data.session_id,combo_key:'c0',reason:'skipped: provider unavailable'},{session_id:p.data.session_id,combo_key:'c1',reason:'failed: provider error'}];
 const view=render(<LineView {...p}/>),row=view.container.querySelector('[data-turn="t3"]') as HTMLElement;
 expect(within(row).getByText('skipped: provider unavailable')).toBeTruthy();expect(within(row).getByText('failed: provider error')).toBeTruthy();expect(within(row).getByText('no line-level output for this turn')).toBeTruthy();
});
it('filters and marks disagreement for the selected combo instead of another combo',()=>{
 const p=props(),a=p.data.combos[0].combo_key,b=p.data.combos[1].combo_key;
 p.data.lanes[b]={missing:null,n:1,repeats:1,turns:{t5:[['sr']]}};
 const view=render(<LineView {...p} state={{...p.state,combo:b,only:'disagree'}}/>);expect(screen.queryByRole('button',{name:'Inspect turn t5'})).toBeNull();
 view.rerender(<LineView {...p} state={{...p.state,combo:a,only:'disagree'}}/>);expect(screen.getByRole('button',{name:'Inspect turn t5'})).toBeTruthy();
 view.rerender(<LineView {...p} state={{...p.state,combo:b}}/>);const row=view.container.querySelector('[data-turn="t5"]') as HTMLElement;expect(within(row).queryByLabelText('Disagreement')).toBeNull();
});
it('shows differing-lines chip count for the selected scope',()=>{
 const p=props();const view=render(<LineView {...p}/>);const n=p.data.turns.filter(t=>p.data.disagreement[t.id]).length;
 expect(view.container.querySelector('.line-differing')?.textContent).toBe(`${n} differing ${n===1?'line':'lines'}`);
 view.rerender(<LineView {...p} state={{...p.state,only:'disagree'}}/>);expect(view.container.querySelector('.line-differing')?.textContent).toBe(`${n} differing ${n===1?'line':'lines'}`);
});
it('filters by session, human code and prediction code through the URL',()=>{
 const p=props();render(<LineView {...p}/>);
 fireEvent.change(screen.getByLabelText('Session'),{target:{value:'uploaded-real-id'}});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({session:'uploaded-real-id',turn:undefined}));
 fireEvent.change(screen.getByLabelText('Human code'),{target:{value:'sr'}});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({code:'sr'}));
 fireEvent.change(screen.getByLabelText('Combo'),{target:{value:p.data.combos[1].combo_key}});expect(p.navigate).toHaveBeenLastCalledWith(expect.objectContaining({combo:p.data.combos[1].combo_key}));
});
it('marks disagreeing rows with a warning chip and text, others unmarked; muted note present',()=>{
 const p=props();const view=render(<LineView {...p}/>);
 const flagged=[...view.container.querySelectorAll('tr.line-disagree')];expect(flagged.length).toBeGreaterThan(0);
 for(const row of flagged){const mark=within(row as HTMLElement).getByLabelText('Disagreement');expect(mark.textContent).toMatch(/Disagrees/);expect(mark.querySelector('.ui-chip-warning svg')).toBeTruthy();}
 const rows=[...view.container.querySelectorAll('tbody tr')];expect(rows.length-flagged.length).toBeGreaterThan(0);
 expect(view.container.querySelector('.ui-note')?.textContent).toMatch(/^How to read:/);
});
it('renders speaker chips, a human lane and one lane chip per combo in a fixed, non-scrolling layout',()=>{
 const p=props();const view=render(<LineView {...p}/>);const row=view.container.querySelector('[data-turn="t5"]') as HTMLElement;
 expect(row.querySelector('td[data-label="Speaker"] .ui-chip')?.textContent).toBe('A');expect(row.querySelector('[data-human]')).toBeTruthy();
 expect(row.querySelectorAll('td[data-label^="Combo "] .line-chip')).toHaveLength(p.data.combos.length);expect([...view.container.querySelectorAll('thead th')].slice(4)).toHaveLength(p.data.combos.length);
 expect(view.container.querySelector('.line-lanes .table-scroll')).toBeNull();
 const css=lineCss;expect(css).toMatch(/table-layout:\s*fixed/);expect(css).not.toMatch(/overflow(-x)?\s*:\s*(auto|scroll)/);expect(css).toMatch(/@media \(max-width: 760px\)[\s\S]*display: block/);
});
it('wraps long unbroken transcript text in a wrapping cell',()=>{
 const p=props();p.data.turns[3].text='x'.repeat(500);const view=render(<LineView {...p}/>);
 const cell=view.container.querySelector('[data-turn="t5"] [data-transcript]') as HTMLElement;expect(cell.textContent).toBe('x'.repeat(500));expect(cell.className).toContain('line-verbatim');
 expect(lineCss).toMatch(/\.line-verbatim[^}]*overflow-wrap:\s*anywhere/);
});
it('composes filters, lanes, one verbatim note, ratings toggle and popup in PRD order with ratings closed',()=>{
 const p=props();const view=render(<LineView {...p}/>);
 const root=view.container.querySelector('.line-view') as HTMLElement;
 const at=(sel:string)=>{const node=root.querySelector(sel);expect(node,sel).toBeTruthy();return node as Element;};
 const before=(a:Element,b:Element)=>expect(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 const filters=at('.line-filters'),lanes=at('.line-lanes'),ratings=at('.line-ratings');
 before(filters,lanes);before(lanes,ratings);
 expect(screen.getByRole('button',{name:'Show global ratings'}).getAttribute('aria-expanded')).toBe('false');
 expect(screen.queryByRole('table',{name:'Session global ratings'})).toBeNull();expect(p.api.compareReasoning).not.toHaveBeenCalled();
 expect(screen.queryByRole('dialog')).toBeNull();expect(root.querySelectorAll('.line-lanes .ui-note')).toHaveLength(1);
});
function fourCombos() {
 const p=props(),first=p.data.combos[0],keys=['c0','c1','c2','c3'];
 const combos=keys.map(key=>({...first,combo_key:key}));
 p.data.combos=combos;p.overview.combos=combos;
 p.overview.count_error=Object.fromEntries(keys.map(key=>[key,structuredClone(Object.values(p.overview.count_error)[0])]));
 return p;
}
it('sends only the shown lanes (at most three) so server disagreement ignores hidden combos',async()=>{
 const p=fourCombos();render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',session:'synthetic-s01',only:'disagree'}} navigate={p.navigate}/>);
 await screen.findByLabelText('Combo');
 expect(p.api.compareLines).toHaveBeenCalledWith('r1','synthetic-s01',expect.objectContaining({combos:['c0','c1','c2']}),expect.any(AbortSignal));
 expect(p.api.compareLines).not.toHaveBeenCalledWith('r1','synthetic-s01',expect.objectContaining({combos:expect.arrayContaining(['c3'])}),expect.any(AbortSignal));
});
it('swaps a navigated combo outside the first three into the shown lanes and selects it',async()=>{
 const p=fourCombos();render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',session:'synthetic-s01',combo:'c3'}} navigate={p.navigate}/>);
 await screen.findByLabelText('Combo');
 expect(p.api.compareLines).toHaveBeenCalledWith('r1','synthetic-s01',expect.objectContaining({combos:['c0','c1','c3'],combo:'c3'}),expect.any(AbortSignal));
 expect((screen.getByLabelText('Combo') as HTMLSelectElement).value).toBe('c3');
});

it('renders popup codes as chips; combo codes disagreeing with the human code are warning chips with text',async()=>{
 const p=props();render(<LineView {...p} state={{...p.state,turn:'t5'}}/>);
 const dialog=await screen.findByRole('dialog');await within(dialog).findByText('withheld');
 const chips=[...dialog.querySelectorAll('.ui-chip')];const sr=chips.filter(c=>c.textContent==='sr'),cr=chips.filter(c=>c.textContent==='cr');
 expect(sr.length).toBeGreaterThanOrEqual(3);expect(sr.every(c=>!c.classList.contains('ui-chip-warning'))).toBe(true);
 expect(cr).toHaveLength(1);expect(cr[0].classList.contains('ui-chip-warning')).toBe(true);expect(cr[0].textContent).toBe('cr');
 expect(dialog.querySelectorAll('.line-dialog-heading').length).toBeGreaterThanOrEqual(2);expect(dialog.querySelector('h3:not(.line-dialog-heading)')).toBeNull();
});
it('defaults lanes to the best three by count error, never a failed combo, when nothing is selected',async()=>{
 const p=fourCombos();const err=(off:number|null)=>({...Object.values(p.overview.count_error)[0],off,na:off===null?{reason:'failed'}:null});
 p.overview.count_error={c0:err(9),c1:err(2),c2:err(5),c3:err(null)};
 render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',session:'synthetic-s01'}} navigate={p.navigate}/>);
 await screen.findByLabelText('Combo');
 expect(p.api.compareLines).toHaveBeenCalledWith('r1','synthetic-s01',expect.objectContaining({combos:['c1','c2','c0']}),expect.any(AbortSignal));
});
it('keeps an explicit combo selection over the best-three default',async()=>{
 const p=fourCombos();const err=(off:number)=>({...Object.values(p.overview.count_error)[0],off,na:null});
 p.overview.count_error={c0:err(9),c1:err(2),c2:err(5),c3:err(1)};
 render(<CompareApp api={p.api} runId="r1" state={{view:'compare',tab:'lines',session:'synthetic-s01',combos:['c0','c1']}} navigate={p.navigate}/>);
 await screen.findByLabelText('Combo');
 expect(p.api.compareLines).toHaveBeenCalledWith('r1','synthetic-s01',expect.objectContaining({combos:['c0','c1']}),expect.any(AbortSignal));
});
