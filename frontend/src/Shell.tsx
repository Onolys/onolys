import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import type { AuthSession } from "./auth";
import { getConfig } from "./config";

type MeState = "loading" | "ok" | "unreachable";

const noUser = { status: "signed-out", user: null } as const;

/**
 * The only page: a header and "Nothing here yet.".
 * With a session it first calls GET {VITE_ADMIN_API_URL}/v1/me through the session fetch, so a signed-in but
 * non-allowlisted account gets a 403 and the AuthGate shows "Not allowed". With no session (gate off) it renders directly.
 */
export function Shell({ session }: { session: AuthSession | null }) {
  const snap = useSyncExternalStore(session ? session.subscribe : () => () => undefined, session ? session.getSnapshot : () => noUser);
  const authedFetch = useMemo(() => (session ? session.createFetch() : null), [session]);
  const [me, setMe] = useState<MeState>(session ? "loading" : "ok");

  const check = useCallback(async () => {
    if (!authedFetch) return;
    setMe("loading");
    try {
      const base = getConfig().adminApiUrl ?? "";
      await authedFetch(`${base}/v1/me`);
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
        {me === "unreachable" ? (
          <div role="alert">
            <p>Could not reach the server.</p>
            <button type="button" onClick={() => void check()}>Retry</button>
          </div>
        ) : null}
      </main>
    </div>
  );
}
