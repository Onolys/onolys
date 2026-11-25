import { useRef, useState, type RefObject } from 'react';
import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@onolys/ui';
import { ApiError, type EvalApi, type RunDetail, type RunSummary } from './api';

export const isActiveRun = (run: Pick<RunSummary, 'status'>) => run.status === 'queued' || run.status === 'running';
export const canCancelRun = (run: RunSummary) => isActiveRun(run) && !run.cancel_requested;
export const CANCELLATION_NOTE = 'Cancelled — runs already in progress will finish; no new runs start.';
/** Preserve a successful request while an older status read catches up. */
export function mergeRunStatus<T extends RunSummary>(previous: T, fresh: T): T {
  return { ...fresh, cancel_requested: isActiveRun(fresh) && Boolean(previous.cancel_requested || fresh.cancel_requested) };
}
export function CancellationNote({ run }: { run: RunSummary }) {
  return run.cancel_requested && isActiveRun(run) ? <p>{CANCELLATION_NOTE}</p> : null;
}
export function CancelRunDialog({ api, run, onClose, onUpdated, returnFocus }: {
  api: EvalApi; run: RunSummary | null; onClose: () => void;
  onUpdated: (run: RunDetail) => void; returnFocus: RefObject<HTMLElement | null>;
}) {
  const lock = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const close = () => { if (!lock.current) { setError(''); onClose(); } };
  const confirm = async () => {
    if (!run || lock.current) return;
    lock.current = true; setPending(true); setError('');
    try {
      let requested = false;
      try { const reply = await api.cancel(run.run_id); requested = isActiveRun(reply); }
      catch (e) { if (!(e instanceof ApiError && e.status === 409)) throw e; }
      const fresh = await api.run(run.run_id);
      onUpdated({ ...fresh, cancel_requested: isActiveRun(fresh) && Boolean(requested || fresh.cancel_requested) });
      onClose();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not cancel run. Please try again.'); }
    finally { lock.current = false; setPending(false); }
  };
  return <Dialog open={run !== null} onOpenChange={open => { if (!open) close(); }}>
    <DialogContent onCloseAutoFocus={event => { event.preventDefault(); returnFocus.current?.focus(); }}>
      <DialogHeader><DialogTitle>Stop this eval run?</DialogTitle><DialogDescription>Runs already finished are kept and can be compared. Runs already in progress will finish; no new runs start.</DialogDescription></DialogHeader>
      {pending && <p role="status">cancelling</p>}
      {error && <div role="alert">{error}<Button disabled={pending} onClick={() => void confirm()}>Retry</Button></div>}
      <DialogFooter><Button variant="ghost" disabled={pending} onClick={close}>Keep running</Button><Button disabled={pending} onClick={() => void confirm()}>Cancel run</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
