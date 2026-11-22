import "./app.css";
import { AuthGate } from "./auth";
import type { AuthSession } from "./auth";
import { Shell } from "./Shell";

/** `session` is null when the gate is off (local dev, VITE_MOCK): the shell mounts with no auth involvement. */
export function Root({ session }: { session: AuthSession | null }) {
  if (!session) return <Shell session={null} />;
  return (
    <AuthGate session={session}>
      <Shell session={session} />
    </AuthGate>
  );
}
