import { Button } from "@onolys/ui";
import { useEffect, useState } from "react";

const COUNTDOWN_S = 5;

/**
 * `Retry (5)…(1)` then `Retry`. Client-only pacing that starts when the card mounts
 * and resets only on remount; the server does not enforce it (the retry cap is the guard).
 * `aria-disabled` rather than `disabled`, so the button stays focusable while counting.
 */
export function RetryButton({ onRetry, pending = false }: { onRetry: () => void; pending?: boolean }) {
  const [left, setLeft] = useState(COUNTDOWN_S);
  useEffect(() => {
    const t = setInterval(() => setLeft((n) => (n > 0 ? n - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, []);
  const locked = left > 0 || pending;
  return (
    <Button
      type="button"
      aria-disabled={locked}
      className={locked ? "opacity-50" : undefined}
      onClick={() => {
        if (!locked) onRetry();
      }}
    >
      {left > 0 ? `Retry (${left})` : "Retry"}
    </Button>
  );
}
