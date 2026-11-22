import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router";

/** `#i=<id>` -> id (ids only, never text); anything else -> null. */
export function parseInstanceHash(hash: string): string | null {
  const m = /^#i=(.+)$/.exec(hash);
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return null;
  }
}

/** Selected instance id lives in the URL hash (via the router) so links and the back button work. */
export function useSelectedInstance(): [string | null, (id: string | null) => void] {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const id = parseInstanceHash(hash);
  const select = useCallback(
    (next: string | null) => {
      // Keep the path and query; an empty selection drops the hash entirely (no bare "#").
      navigate({ hash: next ? `#i=${encodeURIComponent(next)}` : "" }, { preventScrollReset: true });
    },
    [navigate],
  );
  return [id, select];
}
