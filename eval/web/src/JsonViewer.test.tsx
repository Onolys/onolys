// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { JsonDialog, JsonViewer, prettyJson } from './JsonViewer';

afterEach(cleanup);
const value = { alpha: 1, nested: { list: [1, 2, 3] } };

it('never renders JSON inline; the button opens a dialog and Esc / the close button dismiss it', async () => {
  render(<JsonViewer value={value} title="Payload" />);
  expect(screen.queryByText(/alpha/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  const dialog = await screen.findByRole('dialog', { name: 'Payload' });
  expect(within(dialog).getByTestId('json-scroll').textContent).toBe(prettyJson(value));
  fireEvent.keyDown(dialog, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Close' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});
it('shows the JSON in a keyboard-focusable monospace block that scrolls on both axes', async () => {
  render(<JsonViewer value={value} title="Payload" />);
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  const scroll = (await screen.findByTestId('json-scroll')) as HTMLElement;
  expect(scroll.tabIndex).toBe(0);
  expect(scroll.querySelector('pre')).toBeTruthy();
  const css = readFileSync(resolve(import.meta.dirname, 'runs.css'), 'utf8');
  const rule = css.match(/\.eval-config-json \{[^}]*\}/)![0];
  expect(rule).toMatch(/max-height: \d+dvh/);
  expect(rule).toMatch(/overflow: auto/);
  expect(rule).toMatch(/white-space: pre;/);
  expect(css).toMatch(/\.eval-config-json pre \{[^}]*monospace/);
});
it('Copy writes the pretty JSON to the clipboard and confirms', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  render(<JsonViewer value={value} title="Payload" />);
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Copy' }));
  expect(await screen.findByText('Copied.')).toBeTruthy();
  expect(writeText).toHaveBeenCalledWith(prettyJson(value));
});
it('reports a failed copy', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error('no')) } });
  render(<JsonViewer value={value} title="Payload" />);
  fireEvent.click(screen.getByRole('button', { name: 'View JSON' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Copy' }));
  expect(await screen.findByText(/Could not copy/)).toBeTruthy();
});
it('shows loading and error states without JSON, with Retry', () => {
  const retry = vi.fn();
  const { rerender } = render(<JsonDialog open onOpenChange={vi.fn()} title="T" loading />);
  expect(screen.getByText('Loading JSON…')).toBeTruthy();
  expect(screen.queryByTestId('json-scroll')).toBeNull();
  rerender(<JsonDialog open onOpenChange={vi.fn()} title="T" error="Boom" onRetry={retry} />);
  fireEvent.click(screen.getByRole('button', { name: 'Retry JSON' }));
  expect(retry).toHaveBeenCalled();
  expect(screen.queryByTestId('json-scroll')).toBeNull();
});
