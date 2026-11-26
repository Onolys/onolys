// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import { MoreAnalysis } from './MoreAnalysis';
import type { CompareAnalysis, CompareOverview } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import analysis from './fixtures/analysis.json';
import overview from './fixtures/overview.json';
afterEach(cleanup);
function props(data: CompareAnalysis = structuredClone(analysis) as CompareAnalysis): CompareTabProps<CompareAnalysis> {
 return { data, overview: overview as CompareOverview, runId: 'eval-lines', state: { run: 'eval-lines', view: 'compare', tab: 'more', code: 'q', only: 'disagree' }, navigate: vi.fn(), api: createEvalApi('', vi.fn()), legend: data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key })) };
}
it('renders server frontier membership and excludes unpriced points', () => {
 const data=structuredClone(analysis) as CompareAnalysis;
 data.frontier.unpriced.push({combo_key:'unpriced',count_error:9,n:1,cost_per_run_usd:null,na:{reason:'price unavailable'}});
 const {container}=render(<MoreAnalysis {...props(data)}/>);
 expect(container.querySelectorAll('[data-cost-point]')).toHaveLength(2);
 expect(container.querySelectorAll('[data-frontier="true"]')).toHaveLength(1);
 expect(container.querySelector('[data-frontier="true"]')?.getAttribute('data-cost-point')).toBe(data.frontier.points[0].combo_key);
 expect(container.querySelector('[data-cost-point="unpriced"]')).toBeNull();
 expect(screen.getByText(/unpriced.*price unavailable/)).toBeTruthy();
 expect(screen.getByRole('img',{name:'Cost vs accuracy scatter'})).toBeTruthy();
 expect(screen.queryByRole('table',{name:'Cost vs accuracy'})).toBeNull();
});
it('prints baseline and reliability values verbatim from the API', () => {
 render(<MoreAnalysis {...props()}/>);
 expect(screen.getByText(/Needs a second human coder, not in this dataset/)).toBeTruthy();
 const reliability=screen.getByRole('table',{name:'Reliability'});
 expect(within(reliability).getByText(/5 of 9 agree/)).toBeTruthy();
 expect(within(reliability).getAllByText(/75 s/)).toHaveLength(2);
 expect(within(reliability).getAllByText('n=4 · retried 0')).toHaveLength(2);
});
it('keeps head-to-head and interviews behind toggles; opening shows server counts, ties and Line view links', () => {
 const input=props();input.data.head_to_head[0].ties=7;
 render(<MoreAnalysis {...input}/>);
 expect(screen.queryByRole('table',{name:'Head-to-head'})).toBeNull();
 expect(screen.queryByRole('table',{name:'Interviews by combo'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Show head-to-head'}));
 fireEvent.click(screen.getByRole('button',{name:'Show interviews by combo'}));
 const matrix=screen.getByRole('table',{name:'Head-to-head'});
 expect(within(matrix).getByLabelText('A closer than B on 0 of 2 sessions, 7 ties')).toBeTruthy();
 expect(within(matrix).getByLabelText('B closer than A on 2 of 2 sessions, 7 ties')).toBeTruthy();
 const link=screen.getByRole('link',{name:'synthetic-s01'});
 expect(link.getAttribute('href')).toBe('?run=eval-lines&view=compare&tab=lines&session=synthetic-s01');
 fireEvent.click(link);
 expect(input.navigate).toHaveBeenCalledWith({run:'eval-lines',view:'compare',tab:'lines',session:'synthetic-s01'});
 expect(screen.getAllByText(/n=1 · 2 repeats/).length).toBeGreaterThan(0);
});
it('keeps error vs length behind a toggle and switches the axis using server values', () => {
 const {container}=render(<MoreAnalysis {...props()}/>);
 expect(container.querySelector('[data-length-point]')).toBeNull();
 expect(screen.getByRole('button',{name:'Show error vs interview length'}).getAttribute('aria-expanded')).toBe('false');
 fireEvent.click(screen.getByRole('button',{name:'Show error vs interview length'}));
 expect(screen.getByRole('button',{name:'Turns'}).getAttribute('aria-pressed')).toBe('true');
 expect(container.querySelector('[data-length-point]')?.getAttribute('data-x')).toBe('8');
 fireEvent.click(screen.getByRole('button',{name:'Words'}));
 expect(container.querySelector('[data-length-point]')?.getAttribute('data-x')).toBe('32');
});
it('hides human error displays without labels and keeps reliability and baseline', () => {
 const data=structuredClone(analysis) as CompareAnalysis;data.has_human=false;
 const {container}=render(<MoreAnalysis {...props(data)}/>);
 expect(screen.getByText('no human reference')).toBeTruthy();
 expect(container.querySelector('svg[role="img"][aria-label$="scatter"]')).toBeNull();
 expect(screen.queryByRole('button',{name:'Show head-to-head'})).toBeNull();
 expect(screen.getByRole('table',{name:'Reliability'})).toBeTruthy();
 expect(screen.getByText(/Needs a second human coder, not in this dataset/)).toBeTruthy();
});
it('retains failures, level n/a, unavailable cohorts and skipped combo labels', () => {
 const input=props(), key=input.data.combos[0].combo_key;
 input.data.skipped_combos=[key];
 input.data.reliability[key].failures=[{code:'provider_unavailable',count:3}];
 input.data.reliability[key].levels.technical={value:null,n:0,na:{reason:'not enough repeats'}};
 input.data.frontier.dominated=[];
 input.data.frontier.unavailable=[{combo_key:key,n:0,na:{reason:'skipped: provider unavailable'}}];
 render(<MoreAnalysis {...input}/>);
 const reliability=screen.getByRole('table',{name:'Reliability'});
 expect(within(reliability).getByText('3 × provider_unavailable')).toBeTruthy();
 expect(within(reliability).getByText('Technical n/a - not enough repeats · n=0')).toBeTruthy();
 expect(within(reliability).getByText('skipped')).toBeTruthy();
 expect(screen.getByText('A (skipped): n/a - skipped: provider unavailable · n=0')).toBeTruthy();
});
it('keeps zero-valued scatters finite and states when no points can be plotted', () => {
 const input=props();
 input.data.frontier.points[0].count_error=0;
 input.data.frontier.points[0].cost_per_run_usd=0;
 input.data.frontier.dominated=[];
 const view=render(<MoreAnalysis {...input}/>);
 expect(view.container.querySelector('[data-cost-point]')).toBeTruthy();
 expect(view.container.querySelector('[data-cost-label]')?.getAttribute('x')).not.toMatch(/NaN|Infinity/);
 input.data.frontier.points=[];input.data.error_vs_length=[];input.data.grid=[];
 view.rerender(<MoreAnalysis {...input}/>);
 expect(screen.getByText('No priced results available')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Show error vs interview length'}));
 fireEvent.click(screen.getByRole('button',{name:'Show interviews by combo'}));
 expect(screen.getByText('No session length results available')).toBeTruthy();
 expect(screen.getByText('No session results available')).toBeTruthy();
});
it('joins exactly the points the server places on the frontier without choosing winners', () => {
 const input=props();
 input.data.frontier.points.push(...input.data.frontier.dominated);
 input.data.frontier.dominated=[];
 const {container}=render(<MoreAnalysis {...input}/>);
 const line=container.querySelector('.ca-frontier');
 expect([...(line?.getAttribute('data-frontier-combos')?.split(',')??[])].sort()).toEqual(input.data.frontier.points.map(p=>p.combo_key).sort());
 expect(container.querySelectorAll('[data-frontier="true"]')).toHaveLength(2);
});
