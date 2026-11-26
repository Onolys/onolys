import { Ban, Clock, Loader2 } from 'lucide-react';
import type { RunSummary } from '../api';
import { isActiveRun } from '../CancelRunDialog';
import { Chip, type ChipTone } from '../ui/Chip';
import './run.css';

const OVERALL: Record<string, { label: string; tone: ChipTone }> = {
  queued: { label: 'Queued', tone: 'neutral' }, running: { label: 'Running', tone: 'info' }, done: { label: 'Done', tone: 'success' },
  partial: { label: 'Partial', tone: 'warning' }, failed: { label: 'Failed', tone: 'danger' }, cancelled: { label: 'Cancelled', tone: 'muted' }, deleting: { label: 'Deleting', tone: 'muted' },
};
const spin = <Loader2 aria-hidden="true" className="run-spin" />;

/** One chip per state (zero counts muted) plus a progress bar. Overall chip first; running/queued only while the run is active. */
export function RunStatusChips({ run }: { run: RunSummary }) {
  const active = isActiveRun(run);
  const cancelling = active && run.cancel_requested === true;
  const overall = cancelling ? { label: 'Cancelling', tone: 'warning' as const } : OVERALL[run.status] ?? { label: run.status, tone: 'neutral' as const };
  const tone = (n: number, on: ChipTone): ChipTone => n === 0 ? 'muted' : on;
  const running = run.running_units ?? 0, queued = run.queued_units ?? 0;
  const percent = run.total_units > 0 ? Math.min(100, Math.round(run.completed_units / run.total_units * 100)) : 0;
  return <div className="run-status">
    <div className="run-chips" role="status" aria-label="Run status">
      <Chip tone={overall.tone} icon={run.status === 'running' && !cancelling ? spin : undefined}><b>{overall.label}</b></Chip>
      <Chip tone={tone(run.done_units, 'success')}>{`${run.done_units} of ${run.total_units} done`}</Chip>
      {active && <Chip tone={tone(running, 'info')} icon={spin}>{`${running} running`}</Chip>}
      {active && <Chip tone={tone(queued, 'neutral')} icon={<Clock aria-hidden="true" />}>{`${queued} queued`}</Chip>}
      <Chip tone={tone(run.failed_units, 'danger')}>{`${run.failed_units} failed`}</Chip>
      <Chip tone={run.cancelled_units === 0 ? 'muted' : 'neutral'} icon={<Ban aria-hidden="true" />}>{`${run.cancelled_units} cancelled`}</Chip>
    </div>
    <div className="run-progress" role="progressbar" aria-label="Run progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} title={`${percent}% finished`}><i style={{ width: `${percent}%` }} /></div>
  </div>;
}
