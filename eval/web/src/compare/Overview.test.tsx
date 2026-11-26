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
it('keeps skipped combos out of best in the leaderboard',()=>{
 const data=sample();data.leaderboard[0].na={reason:'skipped: provider unavailable'};show(data);
 const skippedRow=within(screen.getAllByRole('table')[0]).getAllByRole('row').find(row=>row.textContent?.includes('skipped'))!;expect(skippedRow.textContent).not.toContain('★ best');
});
it('keeps the metric heatmap collapsed by default and opens it on toggle',()=>{
 show();
 const toggle=screen.getByRole('button',{name:'Show metric heatmap'});
 expect(toggle.getAttribute('aria-expanded')).toBe('false');
 expect(screen.queryByRole('table',{name:'Metric heatmap'})).toBeNull();expect(screen.getAllByRole('table')).toHaveLength(1);
 fireEvent.click(toggle);
 expect(screen.getByRole('table',{name:'Metric heatmap'})).toBeTruthy();
 expect(screen.queryByText(/How to read/)).toBeNull();
 fireEvent.click(toggle);expect(screen.queryByRole('table',{name:'Metric heatmap'})).toBeNull();
});
it.each([false,true])('shows only operational columns and an empty-state chip without human or verdict (%s)',emptyVerdict=>{
 const data=sample();if(emptyVerdict)data.verdict=[];else data.has_human=false;show(data);
 expect(screen.getByText('No human reference in this run').closest('.ui-chip')).toBeTruthy();
 expect(screen.queryByRole('columnheader',{name:'Count error'})).toBeNull();
 for(const name of ['Fails','Cost','Time'])expect(screen.getByRole('columnheader',{name})).toBeTruthy();expect(screen.queryByRole('table',{name:'Metric heatmap'})).toBeNull();
});
it('notes excluded failed combos in muted text and never stars them',()=>{
 const data=sample(),key=data.combos[0].combo_key;
 data.excluded=[1,2,3,4].map(n=>({session_id:`s${n}`,combo_key:key,reason:'failed:invalid_parameters'}));
 show(data);
 expect(screen.getByText(/Excluded from best: A \(all runs failed: invalid_parameters\)/).className).toContain('ui-note');
 expect(screen.getAllByRole('table')[0].querySelector('.ui-row-danger')).toBeTruthy();
});
