/**
 * A hostname with a trailing dot (https://onolys-eval-app.web.app./) is the same site but a different browser
 * Origin, so it is not in the backend's exact CORS_ORIGINS list and every API call fails. Send the user to the
 * dotless host before anything else runs.
 */
export function canonicalHostUrl(href: string): string | null {
  const url = new URL(href);
  if (!url.hostname.endsWith('.')) return null;
  url.hostname = url.hostname.replace(/\.+$/, '');
  return url.href;
}

export function redirectToCanonicalHost(location: { href: string; replace(url: string): void }): boolean {
  const target = canonicalHostUrl(location.href);
  if (!target) return false;
  location.replace(target);
  return true;
}
