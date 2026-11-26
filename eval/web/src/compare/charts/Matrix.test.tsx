// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareAnalysis } from '../compareApi';
import analysis from '../fixtures/analysis.json';
import { HeadToHead } from './HeadToHead';
import { InterviewGrid } from './InterviewGrid';
afterEach(cleanup);
const base = () => structuredClone(analysis) as CompareAnalysis;
const legendFor = (data: CompareAnalysis) => data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key }));
const noFail: { combo_key: string; code: string; runs: number; all: boolean }[] = [];

it('prints directional server head-to-head counts, ties, and a text verdict beside the colour', () => {
 const data = base(); data.head_to_head[0].ties = 7;
 render(<HeadToHead data={data} legend={legendFor(data)} failed={noFail} />);
 const matrix = screen.getByRole('table', { name: 'Head-to-head' });
 const ab = within(matrix).getByLabelText('A closer than B on 0 of 2 sessions, 7 ties');
 const ba = within(matrix).getByLabelText('B closer than A on 2 of 2 sessions, 7 ties');
 expect(ab.textContent).toContain('0 of 2'); expect(ab.textContent).toContain('behind · 7 ties'); expect(ab.getAttribute('data-win-share')).toBe('0');
 expect(ba.textContent).toContain('ahead · 7 ties'); expect(ba.getAttribute('data-win-share')).toBe('1');
 expect(within(matrix).getAllByText('Same combo')).toHaveLength(2);
 expect(screen.getByText(/Ties count for neither combo/)).toBeTruthy();
});

it('greys failed combos in the matrix and never compares them', () => {
 const data = base(); const key = data.combos[0].combo_key;
 render(<HeadToHead data={data} legend={legendFor(data)} failed={[{ combo_key: key, code: 'x', runs: 4, all: true }]} />);
 const matrix = screen.getByRole('table', { name: 'Head-to-head' });
 expect(within(matrix).getAllByText('failed').length).toBeGreaterThan(0);
 expect(matrix.querySelector('[data-verdict]')).toBeNull();
 expect(within(matrix).getAllByText('—').length).toBeGreaterThan(0);
});

it('shows grid values from the fixture and links sessions to Line view', () => {
 const data = base(); const navigate = vi.fn();
 render(<InterviewGrid data={data} legend={legendFor(data)} failed={noFail} runId="eval-lines" navigate={navigate} />);
 const grid = screen.getByRole('table', { name: 'Interviews by combo' });
 expect(within(grid).getAllByText('off 2').length).toBe(1);
 expect(within(grid).getAllByText('n=1 · 2 repeats').length).toBe(data.grid.length * data.combos.length);
 const link = screen.getByRole('link', { name: 'synthetic-s01' });
 expect(link.getAttribute('href')).toBe('?run=eval-lines&view=compare&tab=lines&session=synthetic-s01');
 fireEvent.click(link);
 expect(navigate).toHaveBeenCalledWith({ run: 'eval-lines', view: 'compare', tab: 'lines', session: 'synthetic-s01' });
});

it('marks n/a and failed cells with text, and says so when empty', () => {
 const data = base(); const [a, b] = data.combos.map(c => c.combo_key);
 data.grid[0].cells[a] = { off: null, n: 0, repeats: 0, codes_labeled: 0, observed: data.grid[0].cells[a].observed, na: { reason: 'no completed runs' } };
 const view = render(<InterviewGrid data={data} legend={legendFor(data)} failed={[{ combo_key: b, code: 'x', runs: 4, all: true }]} runId="r" navigate={vi.fn()} />);
 expect(screen.getByText('n/a - no completed runs · n=0')).toBeTruthy();
 expect(within(screen.getByRole('table', { name: 'Interviews by combo' })).getAllByText('—')).toHaveLength(data.grid.length);
 data.grid = [];
 view.rerender(<InterviewGrid data={data} legend={legendFor(data)} failed={[]} runId="r" navigate={vi.fn()} />);
 expect(screen.getByText('No session results available')).toBeTruthy();
});

it('tints cells by win share on a diverging scale and keeps text values', () => {
 const data = base(); const [x, y] = data.combos.map(c => c.combo_key);
 data.combos = [...data.combos, { ...data.combos[0], combo_key: 'third' }];
 data.head_to_head = [
  { a: x, b: y, a_closer: 9, b_closer: 1, ties: 0, n: 10, na: null },
  { a: x, b: 'third', a_closer: 6, b_closer: 4, ties: 0, n: 10, na: null },
 ] as CompareAnalysis['head_to_head'];
 render(<HeadToHead data={data} legend={legendFor(data)} failed={noFail} />);
 const matrix = screen.getByRole('table', { name: 'Head-to-head' });
 const strong = within(matrix).getByLabelText('A closer than B on 9 of 10 sessions, 0 ties') as HTMLElement;
 const weak = within(matrix).getByLabelText('A closer than C on 6 of 10 sessions, 0 ties') as HTMLElement;
 expect(strong.style.backgroundColor).not.toBe('');
 expect(weak.style.backgroundColor).not.toBe('');
 expect(strong.style.backgroundColor).not.toBe(weak.style.backgroundColor);
 expect(strong.textContent).toContain('9 of 10'); expect(weak.textContent).toContain('6 of 10');
 expect(screen.getByText(/Ties count for neither combo/)).toBeTruthy();
});
