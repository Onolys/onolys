import { Settings, SquareArrowOutUpRight } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { Button } from '@onolys/ui';
import type { RunDetail } from '../api';
import { canCancelRun } from '../CancelRunDialog';
import { CompareLink, EvalLink, type CompareNavigate } from '../compare/CompareLink';
import { CopyField } from '../ui/CopyField';
import { runLogsUrl } from './logsUrl';
import './run.css';

const COMPARE_NOTE = 'Compare opens when the run has finished results';

/** Title, muted description and summary card (copyable run id, Logs link, actions). `children` render inside the card (status chips). */
export function RunHeader({ run, onConfig, onRerun, onCancel, onNavigate, children }: {
  run: RunDetail; onConfig: (run: RunDetail, trigger: HTMLElement) => void; onRerun: (run: RunDetail) => void;
  onCancel: (run: RunDetail, trigger: HTMLElement) => void; onNavigate: CompareNavigate; children?: ReactNode;
}) {
  const compareReady = run.status === 'done' || run.status === 'partial';
  const noteId = useId();
  const logs = runLogsUrl(run.units.map(unit => unit.unit_id));
  return <>
    <div className="run-title">
      <h1>{`Run - ${run.name || run.run_id}`}</h1>
    </div>
    {run.description && <p className="run-description">{run.description}</p>}
    <section className="run-card" aria-label="Run summary">
      <div className="run-card-row">
        <CopyField label="Run ID" value={run.run_id} />
        {logs
          ? <a className="run-logs" href={logs.url} target="_blank" rel="noopener noreferrer" title={logs.truncated ? `Showing logs for the first ${logs.used} of ${logs.total} units` : undefined}><SquareArrowOutUpRight aria-hidden="true" />Logs</a>
          : <span className="run-logs is-disabled" aria-disabled="true" title="No logs yet: units have not started"><SquareArrowOutUpRight aria-hidden="true" /><span>Logs</span></span>}
        <div className="run-actions">
          <Button variant="outline" size="sm" className="run-compact" onClick={event => onConfig(run, event.currentTarget)}><Settings aria-hidden="true" />Config</Button>
          {run.status === 'done'
            ? <Button asChild variant="outline" size="sm" className="run-compact run-compare-go"><EvalLink state={{ run: run.run_id, view: 'compare', tab: 'overview' }} navigate={onNavigate}>Compare</EvalLink></Button>
            : compareReady
            ? <CompareLink run={run} navigate={onNavigate} />
            : <><Button variant="outline" size="sm" className="run-compact" disabled title={COMPARE_NOTE} aria-describedby={noteId}>Compare</Button><span id={noteId} hidden>{COMPARE_NOTE}</span></>}
          <Button variant="outline" size="sm" className="run-compact" onClick={() => onRerun(run)}>Rerun…</Button>
          {canCancelRun(run) && <Button variant="outline" size="sm" className="run-compact run-cancel" onClick={event => onCancel(run, event.currentTarget)}>Cancel run</Button>}
        </div>
      </div>
      {children}
    </section>
  </>;
}
