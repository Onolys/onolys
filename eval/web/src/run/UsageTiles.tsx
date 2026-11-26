import { useEffect, useState } from 'react';
import type { RunSummary } from '../api';
import { Disclosure } from '../ui/Disclosure';
import { Note } from '../ui/Note';
import { StatTile } from '../ui/StatTile';
import './run.css';

const number = (n: number) => n.toLocaleString('en-US');
const duration = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
};
const dateText = (iso: string) => { const date = new Date(iso); return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(); };

/** Input/output tokens, est. cost (unpriced detail in a popover) and started/elapsed, plus the muted STT caveat. */
export function UsageTiles({ run, now: fixedNow }: { run: RunSummary; now?: number }) {
  const active = run.status === 'queued' || run.status === 'running';
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    if (!active || fixedNow !== undefined) return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, fixedNow]);
  const now = fixedNow ?? clock;
  const start = Date.parse(run.created_at);
  const end = run.cancelled_at ? Date.parse(run.cancelled_at) : active ? now : NaN;
  const elapsed = Number.isNaN(start) || Number.isNaN(end) ? null : duration(end - start);
  const unpriced = run.unpriced_units;
  return <div className="run-usage">
    <div className="run-tiles">
      <StatTile label="Input tokens" value={number(run.usage.input_tokens)} />
      <StatTile label="Output tokens" value={number(run.usage.output_tokens)} />
      <StatTile label="Est. cost" value={run.cost_usd_est == null ? '—' : `~$${run.cost_usd_est.toFixed(4)}`}
        sub={unpriced > 0 ? <Disclosure label={`${unpriced} unpriced`}>{`${unpriced} ${unpriced === 1 ? 'unit has' : 'units have'} no price data, so the estimate is incomplete.`}</Disclosure> : undefined} />
      <StatTile label="Started" value={dateText(run.created_at)} sub={elapsed ? `Elapsed ${elapsed}` : undefined} />
    </div>
    <Note>Cost is an estimate. Speech-to-text is not included.</Note>
  </div>;
}
