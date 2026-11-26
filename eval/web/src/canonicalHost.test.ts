import { describe, expect, it, vi } from 'vitest';
import { canonicalHostUrl, redirectToCanonicalHost } from './canonicalHost';

describe('canonical host', () => {
  it('strips the trailing dot of an FQDN hostname, keeping path, query and hash', () => {
    expect(canonicalHostUrl('https://onolys-eval-app.web.app./history?run=r1#x')).toBe('https://onolys-eval-app.web.app/history?run=r1#x');
    expect(canonicalHostUrl('https://eval.onolys.com./')).toBe('https://eval.onolys.com/');
  });
  it('keeps the port when stripping', () => {
    expect(canonicalHostUrl('http://localhost.:5173/')).toBe('http://localhost:5173/');
  });
  it.each(['https://onolys-eval-app.web.app/', 'https://eval.onolys.com/x?y=1', 'http://localhost:5173/'])('leaves %s alone', href => {
    expect(canonicalHostUrl(href)).toBeNull();
  });
  it('replaces the location only when the host needs fixing', () => {
    const replace = vi.fn();
    expect(redirectToCanonicalHost({ href: 'https://onolys-eval-app.web.app./', replace })).toBe(true);
    expect(replace).toHaveBeenCalledWith('https://onolys-eval-app.web.app/');
    replace.mockClear();
    expect(redirectToCanonicalHost({ href: 'https://onolys-eval-app.web.app/', replace })).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });
});
