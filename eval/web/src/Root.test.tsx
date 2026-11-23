// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Root } from './Root';
import { createAuthSession } from './auth/session';
import { createFakeProvider } from './auth/fakeProvider';

afterEach(cleanup);
it('never calls the API while signed out', async () => {
  const baseFetch = vi.fn();
  render(<Root session={createAuthSession(createFakeProvider())} baseFetch={baseFetch} />);
  await screen.findByRole('button', { name: 'Sign in' }); expect(baseFetch).not.toHaveBeenCalled();
});
it('checks allowlist before loading the new run screen', async () => {
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 403 }));
  render(<Root session={createAuthSession(createFakeProvider({ email: 'a@example.com' }))} baseFetch={baseFetch} />);
  expect(await screen.findByText('Not allowed')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'New run' })).toBeNull(); expect(baseFetch).toHaveBeenCalledTimes(1);
});
it('a repeated 401 signs out after exactly one token refresh', async () => {
  const provider = createFakeProvider({ email: 'a@example.com' });
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }));
  render(<Root session={createAuthSession(provider)} baseFetch={baseFetch} />);
  await screen.findByRole('button', { name: 'Sign in' }); expect(baseFetch).toHaveBeenCalledTimes(2);
  expect(provider.getIdToken).toHaveBeenLastCalledWith(true);
});
it('loads New run only after an allowed /me response', async () => {
  const baseFetch = vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).endsWith('/me') ? {} : String(input).includes('/options') ? { engines: [], presets: [], defaults: { dataset: { engines: [], presets: [] }, upload: { engines: [], presets: [] } } } : { datasets: [] })));
  render(<Root session={createAuthSession(createFakeProvider({ email: 'a@example.com' }))} baseFetch={baseFetch} />);
  expect(await screen.findByRole('heading', { name: 'New run' })).toBeTruthy();
  await waitFor(() => expect(baseFetch.mock.calls.length).toBe(3));
  expect(String(baseFetch.mock.calls[0][0])).toContain('/v1/me');
});
it('keeps New run hidden on server errors and offers Retry', async () => {
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 500 }));
  render(<Root session={createAuthSession(createFakeProvider({ email: 'a@example.com' }))} baseFetch={baseFetch} />);
  expect(await screen.findByRole('button', { name: 'Retry' })).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'New run' })).toBeNull();
});
it('restores an existing backend run from its URL after reload and handles browser navigation', async () => {
  window.history.replaceState({}, '', '/?run=saved%2Frun');
  const baseFetch = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    return new Response(JSON.stringify(path.endsWith('/me') ? {} : path.includes('/runs/') ? {
      run_id: 'saved/run', status: 'done', completed_units: 0, total_units: 0, failed_units: 0, cancelled_units: 0,
      usage: { input_tokens: 0, output_tokens: 0 }, cost_usd_est: 0, unpriced_units: 0, units: [],
      input: { upload_id: 'saved-upload' }, compare: { has_human: false, metrics: [], sessions: [], aggregates: [], notes: [] },
    } : { runs: [] }));
  });
  const view = render(<Root session={createAuthSession(createFakeProvider({ email: 'a@example.com' }))} baseFetch={baseFetch} />);
  expect(await screen.findByRole('heading', { name: 'Run saved/run' })).toBeTruthy();
  await screen.findByText('Comparison will appear when units are available.');
  expect(baseFetch.mock.calls.some(call => String(call[0]).endsWith('/v1/runs/saved%2Frun'))).toBe(true);
  expect(baseFetch.mock.calls.some(call => String(call[0]).includes('/datasets'))).toBe(false);
  window.history.pushState({}, '', '/?view=history');
  window.dispatchEvent(new PopStateEvent('popstate'));
  expect(await screen.findByRole('heading', { name: 'History' })).toBeTruthy();
  view.unmount(); window.history.replaceState({}, '', '/');
});
