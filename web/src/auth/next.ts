/** `?next=` handling: same-origin paths only (no open redirects). */

/** Pages that are never a sensible post-login target (they would loop or dead-end). */
const BLOCKED = new Set(["/login", "/signup", "/forgot-password", "/auth/action"]);
const BASE = "https://next.invalid";

export function readNext(search: string): string {
  const raw = new URLSearchParams(search).get("next");
  // eslint-disable-next-line no-control-regex -- control chars are stripped by URL parsers, hiding "//host"
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || /[\u0000-\u001f\u007f]/.test(raw)) return "/";
  let url: URL;
  try {
    url = new URL(raw, BASE);
  } catch {
    return "/";
  }
  if (url.origin !== BASE) return "/";
  if (BLOCKED.has(url.pathname.replace(/\/+$/, ""))) return "/";
  return raw;
}

function hasNext(search: string): boolean {
  return readNext(search) !== "/";
}

/** Append the validated `next` from `search` to `path` (omitted when it is just `/`). */
export function withNext(path: string, search: string): string {
  const next = readNext(search);
  return hasNext(search) ? `${path}?next=${encodeURIComponent(next)}` : path;
}

export function loginUrl(pathname: string, search: string): string {
  const target = pathname + search;
  return target === "/" ? "/login" : `/login?next=${encodeURIComponent(target)}`;
}

export function verifyUrl(pathname: string, search: string): string {
  const target = pathname + search;
  return target === "/" ? "/verify-email" : `/verify-email?next=${encodeURIComponent(target)}`;
}

/** Where the verification email's link returns after verifying; keeps `next` so the user lands where they were going. */
export function verifyContinueUrl(origin: string, next = "/"): string {
  return `${origin}/verify-email${next === "/" ? "" : `?next=${encodeURIComponent(next)}`}`;
}
