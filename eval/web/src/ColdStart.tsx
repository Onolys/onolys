import { useEffect, useState } from 'react';
import { Spinner } from '@onolys/ui';

/** The eval backend scales to zero, so the first request can take a while. True once `pending` has lasted `delayMs`. */
export function useSlowPending(pending: boolean, delayMs = 2000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => setSlow(true), delayMs);
    return () => { clearTimeout(timer); setSlow(false); };
  }, [pending, delayMs]);
  return pending && slow;
}

/** Friendly cold-start message. Renders nothing until the request has been pending for `delayMs`, and never on an error. */
export function ColdStartNotice({ pending, delayMs }: { pending: boolean; delayMs?: number }) {
  if (!useSlowPending(pending, delayMs)) return null;
  return <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
    <Spinner />
    <span>Starting the server… this can take a few seconds.</span>
  </p>;
}
