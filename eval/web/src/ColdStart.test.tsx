// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ColdStartNotice } from './ColdStart';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });
const text = /Starting the server/;

it('shows nothing before the threshold and the message after it', () => {
  render(<ColdStartNotice pending />);
  act(() => { vi.advanceTimersByTime(1999); });
  expect(screen.queryByText(text)).toBeNull();
  act(() => { vi.advanceTimersByTime(1); });
  expect(screen.getByRole('status').textContent).toMatch(text);
});
it('hides the message once the request succeeds', () => {
  const view = render(<ColdStartNotice pending />);
  act(() => { vi.advanceTimersByTime(2500); });
  expect(screen.getByText(text)).toBeTruthy();
  view.rerender(<ColdStartNotice pending={false} />);
  expect(screen.queryByText(text)).toBeNull();
});
it('never shows when the request fails before the threshold', () => {
  const view = render(<ColdStartNotice pending />);
  act(() => { vi.advanceTimersByTime(1000); });
  view.rerender(<ColdStartNotice pending={false} />);
  act(() => { vi.advanceTimersByTime(5000); });
  expect(screen.queryByText(text)).toBeNull();
});
it('keeps showing on an already-slow pending request after a rerender', () => {
  const view = render(<ColdStartNotice pending delayMs={500} />);
  act(() => { vi.advanceTimersByTime(600); });
  view.rerender(<ColdStartNotice pending delayMs={500} />);
  expect(screen.getByText(text)).toBeTruthy();
});
