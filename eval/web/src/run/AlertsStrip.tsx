import { Clock, TriangleAlert } from 'lucide-react';
import type { RunDetail } from '../api';
import { CancellationNote, isActiveRun } from '../CancelRunDialog';
import { PartialBadge, ProviderSkipNotices, RunErrorNote, providerName, runErrorMessage } from '../RunStatus';
import './run.css';

/** Merges run-level notices: provider skipped/busy, cancel requested, partial, run error. Renders nothing when there are none. */
export function AlertsStrip({ run }: { run: RunDetail }) {
  const cooldowns = run.provider_cooldowns ?? [];
  const cancelRequested = run.cancel_requested === true && isActiveRun(run);
  const cancelledEmpty = run.status === 'cancelled' && run.done_units === 0;
  const any = cancelledEmpty || run.status === 'partial' || !!run.provider_skips?.length || cooldowns.length > 0 || cancelRequested || runErrorMessage(run) != null;
  if (!any) return null;
  return <div className="run-alerts" aria-label="Run alerts">
    <TriangleAlert aria-hidden="true" className="run-alerts-icon" />
    <div className="run-alerts-body">
      <RunErrorNote run={run} />
      <CancellationNote run={run} />
      {cancelledEmpty && <p>Cancelled — no runs completed.</p>}
      <PartialBadge run={run} />
      <ProviderSkipNotices skips={run.provider_skips} icon={false} />
      {cooldowns.map(cooldown => <p key={cooldown.provider}><Clock aria-hidden="true" className="run-alerts-clock" />{providerName(cooldown.provider)} is busy — waiting to retry</p>)}
    </div>
  </div>;
}
