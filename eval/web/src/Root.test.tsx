// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { navigateEval, Root } from './Root';
import { signedInService, signedOutService } from './testAuth';

afterEach(() => { cleanup(); window.history.replaceState({}, '', '/'); });
it.each(['/', '/?run=r1&view=compare&tab=overview'])('never calls the API while signed out at %s', async path => {
  window.history.replaceState({}, '', path);
  const baseFetch = vi.fn();
  render(<Root service={signedOutService()} baseFetch={baseFetch} />);
  await screen.findByRole('button', { name: 'Log in' }); expect(baseFetch).not.toHaveBeenCalled();
});
it('checks allowlist before loading the new run screen', async () => {
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 403 }));
  render(<Root service={await signedInService()} baseFetch={baseFetch} />);
  expect(await screen.findByText('No access')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'New run' })).toBeNull(); expect(baseFetch).toHaveBeenCalledTimes(1);
});
it('a repeated 401 signs out after exactly one token refresh', async () => {
  const provider = await signedInService();
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }));
  const getToken = vi.spyOn(provider, 'getToken');
  render(<Root service={provider} baseFetch={baseFetch} />);
  await screen.findByRole('button', { name: 'Log in' }); expect(baseFetch).toHaveBeenCalledTimes(2);
  expect(getToken.mock.calls.filter(([force]) => force === true).length).toBe(1);
});
it('loads New run only after an allowed /me response', async () => {
  const baseFetch = vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).endsWith('/me') ? {} : String(input).includes('/options') ? { engines: [], models: [], defaults: { dataset: { engines: [], selection: { models: [], tiers: [], efforts: [] }, label: '' }, upload: { engines: [], selection: { models: [], tiers: [], efforts: [] }, label: '' } } } : { datasets: [] })));
  render(<Root service={await signedInService()} baseFetch={baseFetch} />);
  expect(await screen.findByRole('heading', { name: 'New run' })).toBeTruthy();
  await waitFor(() => expect(baseFetch.mock.calls.length).toBe(3));
  expect(String(baseFetch.mock.calls[0][0])).toContain('/v1/me');
});
it('keeps New run hidden on server errors and offers Retry', async () => {
  const baseFetch = vi.fn().mockResolvedValue(new Response('{}', { status: 500 }));
  render(<Root service={await signedInService()} baseFetch={baseFetch} />);
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
      input: { upload_id: 'saved-upload' },
    } : { runs: [] }));
  });
  const view = render(<Root service={await signedInService()} baseFetch={baseFetch} />);
  expect(await screen.findByRole('heading', { name: 'Run - saved/run' })).toBeTruthy();
  expect(baseFetch.mock.calls.some(call => String(call[0]).endsWith('/v1/runs/saved%2Frun'))).toBe(true);
  expect(baseFetch.mock.calls.some(call => String(call[0]).includes('/datasets'))).toBe(false);
  window.history.pushState({}, '', '/?view=history');
  window.dispatchEvent(new PopStateEvent('popstate'));
  expect(await screen.findByRole('heading', { name: 'History' })).toBeTruthy();
  view.unmount(); window.history.replaceState({}, '', '/');
});

it('offers avatar signout when access is denied', async () => {
  const provider = await signedInService();
  render(<Root service={provider} baseFetch={vi.fn().mockResolvedValue(new Response('{}', { status: 403 }))} />);
  await screen.findByText('No access');
  fireEvent.keyDown(screen.getByRole('button', { name: 'Account menu' }), { key: 'Enter' });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Sign out' }));
  await screen.findByRole('button', { name: 'Log in' });
});

it('restores a rerun draft through history navigation without starting it', async () => {
  const saved = { run_id: 'saved', input: { dataset_id: 'sample', session_ids: ['s1'] }, engines: ['human'], selection: { models: [], tiers: [], efforts: [] }, repeats: 3, name: 'Saved draft', description: 'Keep this context' };
  window.history.replaceState({ initialRun: saved }, '', '/?other=keep');
  const baseFetch = vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes('/options') ? { engines: [{ id: 'human', label: 'Human', engine: 'human', prod: false }], models: [], defaults: { dataset: { engines: [], selection: { models: [], tiers: [], efforts: [] } } } } : String(input).endsWith('/runs') ? { runs: [] } : {})));
  render(<Root service={await signedInService()} baseFetch={baseFetch} />);
  expect((await screen.findByLabelText('Name (optional)') as HTMLInputElement).value).toBe('Saved draft');
  fireEvent.click(screen.getByRole('link', { name: 'History' }));
  await screen.findByRole('heading', { name: 'History' });
  expect(window.location.search).toContain('other=keep');
  window.history.back();
  await waitFor(() => expect((screen.getByLabelText('Name (optional)') as HTMLInputElement).value).toBe('Saved draft'));
  expect((screen.getByLabelText('Runs per cell') as HTMLSelectElement).value).toBe('3');
  expect(baseFetch.mock.calls.every(call => !String(call[0]).endsWith('/rerun'))).toBe(true);
  window.history.replaceState({}, '', '/');
});

it('403 not_allowlisted shows the no-access screen with owner wording and a Sign out button', async () => {
  const body = JSON.stringify({ error: { code: 'not_allowlisted' } });
  render(<Root service={await signedInService()} baseFetch={vi.fn().mockResolvedValue(new Response(body, { status: 403 }))} />);
  expect(await screen.findByText('No access')).toBeTruthy();
  expect(screen.getByText(/Ask the owner/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('button', { name: 'Log in' });
});
it('signed-out login page is the prod login and still never calls the API', async () => {
  const baseFetch = vi.fn();
  render(<Root service={signedOutService()} baseFetch={baseFetch} />);
  await screen.findByRole('heading', { name: 'Log in' });
  expect(window.location.pathname).toBe('/login');
  expect(baseFetch).not.toHaveBeenCalled();
});

it('preserves compare drill-down state during pushState navigation', () => {
 navigateEval({run:'saved/run', view:'compare', tab:'lines', combos:['miti|m/t/e'], session:'s1', turn:'t3', only:'disagree'});
 expect(new URLSearchParams(window.location.search).get('view')).toBe('compare');
 expect(new URLSearchParams(window.location.search).get('session')).toBe('s1');
 expect(new URLSearchParams(window.location.search).get('combos')).toBe('miti|m/t/e');
});
it('opens Compare separately and restores tab URL navigation and browser back',async()=>{
 const overview=(await import('./compare/fixtures/overview.json')).default;
 const analysis=(await import('./compare/fixtures/analysis.json')).default;
 window.history.replaceState({},'', '/?run=r1&view=compare&tab=overview');
 const baseFetch=vi.fn(async(input:RequestInfo|URL)=>{
  const path=String(input);return new Response(JSON.stringify(path.includes('/compare/overview')?overview:path.includes('/compare/analysis')?analysis:path.endsWith('/me')?{}:{run_id:'r1',status:'done',input:{dataset_id:'saved',session_ids:['s1']},combo_labels:{},units:[]}));
 });
 render(<Root service={await signedInService()} baseFetch={baseFetch}/>);
 expect(await screen.findByRole('heading',{name:'Compare - Synthetic lines'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Unit progress'})).toBeNull();
 fireEvent.click(screen.getByRole('tab',{name:'More analysis'}));await waitFor(()=>expect(window.location.search).toContain('tab=more'));
 await waitFor(()=>expect(screen.getByRole('tab',{name:'More analysis'}).getAttribute('aria-selected')).toBe('true'));
 window.history.back();await waitFor(()=>expect(screen.getByRole('tab',{name:'Overview'}).getAttribute('aria-selected')).toBe('true'));
});

it('eval login has no sign-up or recovery links and tells users to ask the team', async () => {
  window.history.replaceState({}, '', '/login?next=%2F%3Fview%3Dhistory');
  const baseFetch = vi.fn();
  render(<Root service={signedOutService()} baseFetch={baseFetch} />);
  await screen.findByRole('heading', { name: 'Log in' });
  expect(screen.queryByRole('link', { name: 'Create an account' })).toBeNull();
  expect(screen.queryByText(/New here/)).toBeNull();
  expect(screen.queryByRole('link', { name: 'Forgot your password?' })).toBeNull();
  expect(screen.getByText('Ask the Onolys team for an eval account.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Log in' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Continue with Google' })).toBeNull();
  expect(baseFetch).not.toHaveBeenCalled();
});

it.each(['/signup', '/forgot-password', '/verify-email', '/auth/action'])('%s is not handed to the prod app: signed out it lands on login', async path => {
  window.history.replaceState({}, '', path);
  render(<Root service={signedOutService()} baseFetch={vi.fn()} />);
  await screen.findByRole('button', { name: 'Log in' });
  expect(screen.queryByText(/Continuing in the/)).toBeNull();
  expect(screen.queryByRole('link', { name: 'Onolys app' })).toBeNull();
});

it('an unverified account lands on a static not-verified page (no redirect loop) with Sign out', async () => {
  const provider = await signedInService(false);
  const baseFetch = vi.fn();
  render(<Root service={provider} baseFetch={baseFetch} />);
  expect(await screen.findByText("Your eval account isn't verified. Ask the Onolys team.")).toBeTruthy();
  expect(window.location.pathname).toBe('/verify-email');
  expect(baseFetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('button', { name: 'Log in' });
});
