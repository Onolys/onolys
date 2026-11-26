// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { LineMetrics } from '../compareApi';
import type { DotSeries } from './dotPlotLayout';
import { ConfusionGrid } from './ConfusionGrid';
afterEach(cleanup);
const series: DotSeries[] = [{ key: 'a', letter: 'A', index: 0, label: 'A-label' }, { key: 'b', letter: 'B', index: 1, label: 'B-label' }];
const base = { lane: null, n: 5, repeats: 2, per_code: {}, macro_f1: null, line_accuracy: null };
const combos: LineMetrics['combos'] = {
  a: { ...base, aligned: 12, confusion: { q: { q: 6, none: 1.5 }, sr: { sr: 3, cr: 0 } }, multi: 1.5 },
  b: { ...base, aligned: 5, confusion: { none: { none: 2 } }, multi: 3 },
};
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Show confusion grid' }));
const setup = (extra: Partial<Parameters<typeof ConfusionGrid>[0]> = {}) => {
  const onMatch = vi.fn(), onSwitch = vi.fn();
  const view = render(<ConfusionGrid combos={combos} series={series} onMatch={onMatch} onSwitch={onSwitch} {...extra} />);
  return { view, onMatch, onSwitch };
};

it('is collapsed by default and opens on request', () => {
  const { view } = setup();
  expect(view.container.querySelector('.deep-confusion')).toBeNull();
  expect(screen.getByRole('button', { name: 'Show confusion grid' }).getAttribute('aria-expanded')).toBe('false');
  open();
  expect(screen.getByRole('table', { name: 'Confusion grid' })).toBeTruthy();
});
it('lays out human rows by combo columns with a multi row and totals equal to the aligned lines', () => {
  const { view } = setup(); open();
  const values = [...view.container.querySelectorAll('[data-confusion-value]')].reduce((sum, node) => sum + Number(node.getAttribute('data-confusion-value')), 0);
  expect(values).toBe(combos.a.aligned);
  expect(view.container.querySelector('[data-confusion-multi]')!.textContent).toBe('1.5');
  expect(screen.getByRole('rowheader', { name: 'q' })).toBeTruthy();
  expect(screen.getAllByRole('columnheader').map(h => h.textContent)).toEqual(['Human / A', 'q', 'none', 'sr', 'cr']);
});
it('switches the displayed combo and keeps its multi bucket', () => {
  const { view, onSwitch } = setup(); open();
  fireEvent.click(within(screen.getByRole('group', { name: 'Confusion combo' })).getByRole('button', { name: 'Combo B' }));
  expect(onSwitch).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Human none, B none: 2' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Human q, A q/ })).toBeNull();
  expect(view.container.querySelector('[data-confusion-multi]')!.textContent).toBe('3');
  expect(screen.getByText(/Confusion · combo B/)).toBeTruthy();
});
it('calls onMatch with the combo, human code and predicted code for a cell, and for multi', () => {
  const { onMatch, view } = setup(); open();
  fireEvent.click(screen.getByRole('button', { name: 'Human q, A none: 1.5' }));
  expect(onMatch).toHaveBeenLastCalledWith({ combo: 'a', code: 'q', metric: 'none' });
  fireEvent.click(view.container.querySelector('[data-confusion-multi]')!);
  expect(onMatch).toHaveBeenLastCalledWith({ combo: 'a', code: 'multi', metric: 'multi' });
});
it('disables empty cells and keeps tone text so confusion is not colour only', () => {
  const { onMatch } = setup(); open();
  const empty = screen.getByRole('button', { name: 'Human sr, A cr: 0' });
  expect(empty).toHaveProperty('disabled', true);
  fireEvent.click(empty);
  expect(onMatch).not.toHaveBeenCalled();
  expect(screen.getByText(/agree/)).toBeTruthy();
  expect(screen.getByText(/confused/)).toBeTruthy();
});
it('keeps the data twin behind Show data', () => {
  setup(); open();
  expect(screen.queryByRole('table', { name: 'Confusion data' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show data' }));
  expect(screen.getByRole('table', { name: 'Confusion data' }).textContent).toContain('multi');
});
