// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareOverview } from '../compareApi';
import overviewFixture from '../fixtures/overview.json';
import { ComboSelector, pairedSessions } from './ComboSelector';
afterEach(cleanup);
const overview = () => structuredClone(overviewFixture) as CompareOverview;
const mk = (key: string, letter: string) => ({ letter, label: `${letter}-label`, combo: { combo_key: key, engine: 'e', model: null, tier: null, effort: null } });
const legend = [mk('a', 'A'), mk('b', 'B'), mk('c', 'C')];
const failed = [{ combo_key: 'c', code: 'invalid_parameters', runs: 2, all: true }];

it('shows Human as always on, toggles for each combo, and reflects the default selection', () => {
  render(<ComboSelector legend={legend} failed={failed} selected={['a', 'b']} paired={{ n: 2, of: 2 }} onChange={vi.fn()} />);
  const human = screen.getByRole('button', { name: /Human/ });
  expect(human.getAttribute('aria-pressed')).toBe('true');
  expect(human).toHaveProperty('disabled', true);
  expect(screen.getByRole('button', { name: 'A · A-label' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'B · B-label' }).getAttribute('aria-pressed')).toBe('true');
});
it('toggles combos on and off through onChange, keeping at least one selected', () => {
  const onChange = vi.fn();
  const view = render(<ComboSelector legend={legend} failed={[]} selected={['a']} paired={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole('button', { name: 'B · B-label' }));
  expect(onChange).toHaveBeenLastCalledWith(['a', 'b']);
  expect(screen.getByRole('button', { name: 'A · A-label' })).toHaveProperty('disabled', true);
  view.rerender(<ComboSelector legend={legend} failed={[]} selected={['a', 'b']} paired={null} onChange={onChange} />);
  fireEvent.click(screen.getByRole('button', { name: 'A · A-label' }));
  expect(onChange).toHaveBeenLastCalledWith(['b']);
});
it('greys out and disables a failed combo with its error code, never selectable', () => {
  const onChange = vi.fn();
  render(<ComboSelector legend={legend} failed={failed} selected={['a']} paired={null} onChange={onChange} />);
  const button = screen.getByRole('button', { name: /C · C-label/ });
  expect(button).toHaveProperty('disabled', true);
  expect(button.getAttribute('aria-pressed')).toBe('false');
  expect(button.textContent).toContain('failed: invalid_parameters');
  fireEvent.click(button);
  expect(onChange).not.toHaveBeenCalled();
});
it('prints a paired chip as text and omits it without data', () => {
  const view = render(<ComboSelector legend={legend} failed={[]} selected={['a']} paired={{ n: 1, of: 5 }} onChange={vi.fn()} />);
  expect(screen.getByText('paired 1 of 5 sessions')).toBeTruthy();
  view.rerender(<ComboSelector legend={legend} failed={[]} selected={['a']} paired={null} onChange={vi.fn()} />);
  expect(screen.queryByText(/paired/)).toBeNull();
});
it('derives paired x of y from the selected non-failed combos count error cells', () => {
  const ov = overview();
  const keys = ov.combos.map((c) => c.combo_key);
  ov.count_error[keys[0]] = { ...ov.count_error[keys[0]], n: 1, of: 2 };
  expect(pairedSessions(ov, keys)).toEqual({ n: 1, of: 2 });
  expect(pairedSessions(ov, [])).toBeNull();
});
