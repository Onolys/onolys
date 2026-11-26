import { useRef, useState } from 'react';
import { Lightbulb, SquareArrowOutUpRight } from 'lucide-react';
import type { RunDetail, RunUnit } from '../api';
import { AppDialog } from '../ui/AppDialog';
import { Chip } from '../ui/Chip';
import { CopyField } from '../ui/CopyField';
import { Note } from '../ui/Note';
import { describeError } from './errorCatalog';
import { unitLogsUrl } from './logsUrl';
import './run.css';

/** Danger-chip badge for a failed unit; opens the error popup (catalog explanation, fix hint, copyable ids, per-unit Logs link). */
export function UnitErrorBadge({ unit, code }: { run: RunDetail; unit: RunUnit; code?: string }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const info = describeError(code);
  const logs = unitLogsUrl(unit.unit_id);
  return <>
    <button type="button" ref={trigger} className="run-error-badge" aria-label="View error details" onClick={() => setOpen(true)}><Chip tone="danger">{info.title}</Chip></button>
    <AppDialog open={open} onOpenChange={setOpen} title={`Unit ${unit.unit_id} failed`} returnFocus={trigger}
      description="This unit did not finish. Here is what the error code means and what to try next.">
      <div className="run-error-body">
        <div className="run-chips">
          <Chip tone="danger" mono>{info.code || 'unknown'}</Chip>
          {unit.stage ? <Chip tone="neutral">{unit.stage}</Chip> : null}
        </div>
        <div><h3 className="run-error-title">{info.title}</h3><p>{info.explanation}</p></div>
        <p className="run-error-fix"><Lightbulb aria-hidden="true" /><span><b>What to try:</b> {info.fix}</span></p>
        <CopyField label="Unit id" value={unit.unit_id} />
        <CopyField label="Session id" value={unit.session_id} />
        <CopyField label="Error code" value={info.code || 'unknown'} />
        {logs
          ? <a className="run-logs" href={logs} target="_blank" rel="noopener noreferrer"><SquareArrowOutUpRight aria-hidden="true" />Logs</a>
          : <span className="run-logs is-disabled" aria-disabled="true" title="No logs yet: this unit has no worker run id"><SquareArrowOutUpRight aria-hidden="true" /><span>Logs</span></span>}
        <Note>Only the error code is stored, never the full message (it could contain patient information). Open the unit logs for details.</Note>
      </div>
    </AppDialog>
  </>;
}
