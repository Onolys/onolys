// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ErrorBoundary, ErrorPage } from './ErrorPage';
import { Root } from './Root';
import { createFakeAuthService } from '@prod-auth/fakeService';

afterEach(() => { cleanup(); window.history.replaceState({}, '', '/'); });

it('404 page names the problem and links back to New Run', () => {
  render(<ErrorPage notFound />);
  expect(screen.getByRole('heading', { name: 'Page not found' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Back to New Run' }).getAttribute('href')).toBe('/');
});
it('generic error page offers reload', () => {
  const reload = vi.fn();
  render(<ErrorPage reload={reload} />);
  fireEvent.click(screen.getByRole('button', { name: 'Reload page' }));
  expect(reload).toHaveBeenCalled();
  expect(screen.getByRole('alert')).toBeTruthy();
});
it('error boundary replaces a crashing child with the generic page and hides the exception message', () => {
  const quiet = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  const Boom = () => { throw new Error('secret detail'); };
  render(<ErrorBoundary standalone><Boom /></ErrorBoundary>);
  expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeTruthy();
  expect(screen.queryByText(/secret detail/)).toBeNull();
  expect(screen.getByRole('main')).toBeTruthy();
  quiet.mockRestore();
});
it.each(['/nope', '/a/b'])('unknown path %s renders the 404 page inside the shell when signed in', async path => {
  window.history.replaceState({}, '', path);
  const service = createFakeAuthService();
  service.signedInAs('a@example.com', { verified: true });
  const baseFetch = vi.fn();
  render(<Root service={service} baseFetch={baseFetch} />);
  expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeTruthy();
  expect(screen.getByRole('navigation', { name: 'Main' })).toBeTruthy();
  expect(baseFetch).not.toHaveBeenCalled();
});
