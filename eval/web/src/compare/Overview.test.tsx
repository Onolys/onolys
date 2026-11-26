// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import type { CompareOverview } from './compareApi';
import { Overview } from './Overview';
import { parseCompareUrl } from './compareUrl';
import fixture from './fixtures/overview.json';
afterEach(cleanup);
const sample = () => structuredClone(fixture) as CompareOverview;
function show(data = sample()) {
 const navigate = vi.fn();
 render(<Overview data={data} overview={data} state={parseCompareUrl('?run=r1&view=compare')} navigate={navigate} legend={data.combos.map((combo,i)=>({combo,letter:String.fromCharCode(65+i),label:combo.combo_key}))} api={createEvalApi('',vi.fn())} runId="r1"/>);
 return navigate;
}
const cell = (metric:string, combo='A') => screen.getByRole('link',{name:`${metric}, ${combo}: open Deep dive`}).closest('td')!;
it('prints verbatim verdict with n tags and one muted notes block; leaderboard has plain headers',()=>{
 const data=sample();show(data);
 expect(screen.getByText(data.verdict[0].text)).toBeTruthy();expect(screen.getByText('n=2',{selector:'.overview-claim'})).toBeTruthy();
 const note=screen.getByText(/Sessions have equal weight; repeats are averaged first/);expect(note.className).toContain('ui-note');
 expect(screen.getByText(/Time may read short for retried units/)).toBeTruthy();expect(screen.queryByText(/retried_runs counts/)).toBeNull();
 expect(within(screen.getAllByRole('table')[0]).queryAllByRole('button')).toHaveLength(0);
 for(const name of ['Count error','Globals within ±1','Line match accuracy','Line match macro F1','Fails','Cost','Time']) expect(within(screen.getAllByRole('table')[0]).getByRole('columnheader',{name})).toBeTruthy();
 expect(within(screen.getAllByRole('table')[0]).getAllByText(/★ best/).length).toBeGreaterThan(0);
 expect(within(screen.getAllByRole('table')[0]).getAllByText(/no line-level output/).length).toBe(2);
});
it('renders raw Human first, every n, four off headlines, signed bias and server tolerance flags',()=>{
 const data=sample(),a=data.combos[0].combo_key;
 Object.assign(data.heatmap.cells.gi[a],{off:0.6,bias:0.4,n:1,within_tolerance:true,best:false});
 Object.assign(data.heatmap.cells.persuade[a],{off:0.61,bias:-0.4,within_tolerance:false});
 Object.assign(data.heatmap.cells.cct[a],{off:0.4,within_tolerance:true});Object.assign(data.heatmap.cells.sst[a],{off:0.41,within_tolerance:false});
 Object.assign(data.heatmap.cells.affirm[a],{off:9,within_tolerance:true});show(data);
 const heatmap=screen.getByRole('table',{name:'Metric heatmap'});
 expect(within(heatmap).getAllByRole('columnheader').map(x=>x.textContent)).toEqual(['Metric','Human','A','B']);
 expect(within(heatmap).getAllByRole('rowheader')[0].className).toContain('overview-row-label');expect(within(heatmap).getAllByText('synthetic-s01: 1').length).toBeGreaterThan(0);
 expect(cell('gi').className).toContain('within-tolerance');expect(cell('gi').textContent).toContain('n=1');expect(cell('gi').textContent).toContain('off 0.6 · +0.4');
 expect(cell('persuade').className).not.toContain('within-tolerance');expect(cell('persuade').textContent).toContain('-0.4');
 expect(cell('cct').className).toContain('within-tolerance');expect(cell('sst').className).not.toContain('within-tolerance');expect(cell('affirm').className).toContain('within-tolerance');
 for(const metric of ['cct','sst','partnership','empathy'])expect(cell(metric).querySelector('strong')?.textContent).toMatch(/^off /);
 for(const metric of ['R:Q','%CR']){expect(cell(metric).className).not.toContain('within-tolerance');expect(cell(metric,'B').textContent).toContain('best');}
 within(heatmap).getAllByRole('cell').forEach(td=>expect(td.textContent).toMatch(/n=\d/));expect(screen.getByText(/no tolerance set for ratios/)).toBeTruthy();
});
it('keeps exact missing reasons and suppresses all skipped best markers',()=>{
 const data=sample(),key=data.combos[0].combo_key;data.leaderboard[0].na={reason:'skipped: provider unavailable'};
 Object.values(data.heatmap.cells).forEach(row=>Object.assign(row[key],{value:null,off:null,bias:null,na:{reason:'skipped: provider unavailable'},best:true}));show(data);
 const skippedRow=within(screen.getAllByRole('table')[0]).getAllByRole('row').find(row=>row.textContent?.includes('skipped'))!;expect(skippedRow.textContent).not.toContain('★ best');
 expect(cell('gi').textContent).toContain('n/a');expect(cell('gi').textContent).toContain('skipped: provider unavailable');expect(cell('gi').textContent).not.toContain('best');
});
it('labels the nine-combo scroll region and drills into Deep dive with selected metric and combo',()=>{
 const data=sample(),base=data.combos[0];for(let i=2;i<9;i++){const combo={...base,combo_key:`combo-${i}`};data.combos.push(combo);data.leaderboard.push({...data.leaderboard[0],combo_key:combo.combo_key});Object.values(data.heatmap.cells).forEach(row=>{row[combo.combo_key]={...row[base.combo_key]};});}
 const navigate=show(data),region=screen.getByRole('region',{name:'Metric heatmap, scroll horizontally for more combos'});
 expect(region.getAttribute('tabindex')).toBe('0');expect(region.className).toContain('overview-many-combos');
 const link=screen.getByRole('link',{name:'gi, A: open Deep dive'});expect(link.getAttribute('href')).toContain('metric=gi');fireEvent.click(link);
 expect(navigate).toHaveBeenCalledWith(expect.objectContaining({tab:'deep',metric:'gi',combos:[base.combo_key]}));
 fireEvent.click(within(screen.getByRole('table',{name:'Metric heatmap'})).getByRole('link',{name:'A'}));expect(navigate).toHaveBeenLastCalledWith(expect.objectContaining({tab:'deep',combos:[base.combo_key]}));
 expect(screen.getByText(/How to read:/)).toBeTruthy();
});
it.each([false,true])('shows only operational columns and an empty-state chip without human or verdict (%s)',emptyVerdict=>{
 const data=sample();if(emptyVerdict)data.verdict=[];else data.has_human=false;show(data);
 expect(screen.getByText('No human reference in this run').closest('.ui-chip')).toBeTruthy();
 expect(screen.queryByRole('columnheader',{name:'Count error'})).toBeNull();
 for(const name of ['Fails','Cost','Time'])expect(screen.getByRole('columnheader',{name})).toBeTruthy();expect(screen.queryByRole('table',{name:'Metric heatmap'})).toBeNull();
});
it('shows a partial-label reason as n/a rather than a zero headline',()=>{
 const data=sample(),key=data.combos[0].combo_key;
 Object.assign(data.heatmap.cells.gi[key],{value:null,off:null,bias:null,n:0,best:false,within_tolerance:null,na:{reason:'not labeled in this dataset'}});show(data);
 expect(cell('gi').querySelector('strong')?.textContent).toBe('n/a');expect(cell('gi').textContent).toContain('not labeled in this dataset');expect(cell('gi').textContent).toContain('n=0');
});

it('notes excluded failed combos in muted text and never stars them',()=>{
 const data=sample(),key=data.combos[0].combo_key;
 data.excluded=[1,2,3,4].map(n=>({session_id:`s${n}`,combo_key:key,reason:'failed:invalid_parameters'}));
 show(data);
 expect(screen.getByText(/Excluded from best: A \(all runs failed: invalid_parameters\)/).className).toContain('ui-note');
 expect(screen.getAllByRole('table')[0].querySelector('.ui-row-danger')).toBeTruthy();
});
