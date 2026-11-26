import { Badge } from '@onolys/ui';
import type { RunSummary } from './api';

export type PartialRunStatus = Pick<RunSummary, 'status' | 'cancelled_at' | 'done_units' | 'total_units' | 'skipped_units'>;
export type ProviderSkip = { provider: string; after_failures: number };
const providerNames: Record<string, string> = { gemini: 'Gemini', google: 'Google', openai: 'OpenAI', anthropic: 'Anthropic', azure: 'Azure' };
export const providerName = (id: string) => Object.hasOwn(providerNames, id) ? providerNames[id] : id;
const dateText = (iso: string) => { const date = new Date(iso); return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(); };
export function partialStatusText(run: PartialRunStatus): string | null {
  if (run.status !== 'partial') return null;
  return `Partial — ${run.cancelled_at ? `cancelled at ${dateText(run.cancelled_at)}, ` : ''}${run.done_units} of ${run.total_units} runs done${(run.skipped_units ?? 0) > 0 ? `, ${run.skipped_units} skipped` : ''}`;
}
const runErrorText: Record<string, string> = { enqueue_failed: 'Run failed to start: could not queue it for processing. Rerun to try again.' };
export function runErrorMessage(run: Pick<RunSummary, 'status' | 'error'>): string | null {
  if (run.status !== 'failed' || !run.error) return null;
  return runErrorText[run.error.code] ?? `Run failed: ${run.error.code}`;
}
export function RunErrorNote({ run }: { run: Pick<RunSummary, 'status' | 'error'> }) {
  const message = runErrorMessage(run);
  return message ? <p role="alert">{message}</p> : null;
}
export function PartialBadge({ run, short = false }: { run: PartialRunStatus; short?: boolean }) {
  const text = partialStatusText(run);
  if (!text) return null;
  if (short) return <><Badge variant="outline" data-partial-badge><span aria-hidden="true">◐ </span>Partial</Badge><p className="text-sm text-muted-foreground" data-partial-detail>{text.replace(/^Partial — /, '')}</p></>;
  return <Badge variant="outline" className="max-w-full whitespace-normal" data-partial-badge><span aria-hidden="true">◐ </span>{text}</Badge>;
}
export function ProviderSkipNotices({ skips, short = false, icon = true }: { skips?: readonly ProviderSkip[]; short?: boolean; icon?: boolean }) {
  if (!skips?.length) return null;
  return <div data-provider-skips>{skips.map(skip => <p key={skip.provider}>{icon && <span aria-hidden="true">⚠ </span>}{providerName(skip.provider)} skipped after {skip.after_failures} failures{!short && ' in a row — provider may be down'}</p>)}</div>;
}
