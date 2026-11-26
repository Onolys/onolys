// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { RunUnit } from '../api';
import { unitLogsUrl } from './logsUrl';
import { UnitErrorBadge } from './UnitErrorDialog';

afterEach(cleanup);
const unit = (patch: Partial<RunUnit> = {}): RunUnit => ({ unit_id: 'abc123', session_id: 's1', engine: 'miti', status: 'failed', stage: 'coding', error: { code: 'invalid_parameters' }, ...patch });
const show = (u = unit()) => render(<UnitErrorBadge unit={u} code={typeof u.error === 'string' ? u.error : u.error?.code} />);
const open = () => { const b = screen.getByRole('button', { name: /error details/i }); fireEvent.click(b); return b; };

it('badge is a danger chip button showing the error code', () => {
  show();
  const b = screen.getByRole('button', { name: /error details/i });
  expect(b.querySelector('.ui-chip-danger')).toBeTruthy();
  expect(b.textContent).toBe('invalid_parameters');
  expect(screen.queryByRole('dialog')).toBeNull();
});
it('known code: popup title with unit id, chips, explanation, fix, copyable ids, PHI note', () => {
  show(); open();
  const d = screen.getByRole('dialog', { name: 'Unit abc123 failed' });
  expect(within(d).getAllByText('invalid_parameters')).toHaveLength(2);
  expect(within(d).getByText('coding')).toBeTruthy();
  expect(within(d).getByText(/engine rejected the parameters/)).toBeTruthy();
  expect(within(d).getByText(/Check the run config/)).toBeTruthy();
  expect(within(d).getByRole('button', { name: 'Copy unit id' })).toBeTruthy();
  expect(within(d).getByRole('button', { name: 'Copy session id' })).toBeTruthy();
  expect(within(d).getByRole('button', { name: 'Copy error code' })).toBeTruthy();
  expect(d.querySelector('.ui-note')?.textContent).toMatch(/Only the error code is stored/);
});
it('unknown code shows the code and a generic hint', () => {
  show(unit({ error: { code: 'weird_thing' } })); open();
  const d = screen.getByRole('dialog');
  expect(within(d).getAllByText('weird_thing').length).toBeGreaterThan(0);
  expect(within(d).getByText(/not recognised/)).toBeTruthy();
  expect(within(d).getByText(/Rerun the unit/)).toBeTruthy();
});
it('copy writes the unit id', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  show(); open();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy unit id' })); });
  expect(writeText).toHaveBeenCalledWith('abc123');
});
it('Logs link points at the unit logs; placeholder ids get a disabled hint', () => {
  show(); open();
  const link = screen.getByRole('link', { name: /Logs/ });
  expect(link.getAttribute('href')).toBe(unitLogsUrl('abc123'));
  expect(link.getAttribute('target')).toBe('_blank');
  cleanup();
  show(unit({ unit_id: 'cell-9' })); open();
  expect(screen.queryByRole('link', { name: /Logs/ })).toBeNull();
  const off = screen.getByText('Logs').closest('[aria-disabled="true"]')!;
  expect(off.getAttribute('title')).toMatch(/No logs/);
});
it('focus returns to the badge on close', async () => {
  show(); const b = open();
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  await act(async () => {});
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(b);
});
