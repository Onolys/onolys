import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import type { AuthSession } from "./auth";
import { getConfig } from "./config";

type MeState = "loading" | "ok" | "unreachable" | "rate_limited" | "unexpected" | "config";

const noUser = { status: "signed-out", user: null } as const;

/**
 * The only page: a header and "Nothing here yet.".
 * With a session it first calls GET {VITE_ADMIN_API_URL}/v1/me through the session fetch, so a signed-in but
 * non-allowlisted account gets a 403 and the AuthGate shows "Not allowed". With no session (gate off) it renders directly.
 * Only a 2xx JSON answer counts as ok: an HTML 200 (SPA rewrite), 404 or 429 is an error state, and a session without an API URL is a config error.
 */
export function Shell({ session }: { session: AuthSession | null }) {
  const snap = useSyncExternalStore(session ? session.subscribe : () => () => undefined, session ? session.getSnapshot : () => noUser);
  const authedFetch = useMemo(() => (session ? session.createFetch() : null), [session]);
  const [me, setMe] = useState<MeState>(session ? "loading" : "ok");

  const check = useCallback(async () => {
    if (!authedFetch) return;
    const base = getConfig().adminApiUrl;
    if (!base) {
      setMe("config");
      return;
    }
    setMe("loading");
    try {
      const res = await authedFetch(`${base}/v1/me`);
      if (res.status >= 500) return setMe("unreachable");
      if (res.status === 429) return setMe("rate_limited");
      if (!res.ok) return setMe("unexpected");
      try {
        await res.json();
      } catch {
        return setMe("unexpected");
      }
      setMe("ok");
    } catch {
      setMe("unreachable");
    }
  }, [authedFetch]);

  useEffect(() => {
    void check();
  }, [check]);

  return (
    <div className="shell">
      <header className="shell-header">{snap.user?.email ? <span className="shell-email">{snap.user.email}</span> : null}</header>
      <main className="shell-main">
        {me === "ok" ? <p>Nothing here yet.</p> : null}
        {me === "config" ? (
          <div role="alert">
            <p>This build is not configured: VITE_ADMIN_API_URL is missing.</p>
          </div>
        ) : null}
        {me === "unreachable" || me === "rate_limited" || me === "unexpected" ? (
          <div role="alert">
            <p>
              {me === "unreachable"
                ? "Could not reach the server."
                : me === "rate_limited"
                  ? "Too many requests. Wait a moment and retry."
                  : "Unexpected response from the server."}
            </p>
            <button type="button" onClick={() => void check()}>Retry</button>
          </div>
        ) : null}
      </main>
    </div>
  );
}
