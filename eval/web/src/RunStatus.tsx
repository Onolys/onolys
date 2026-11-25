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
export function PartialBadge({ run }: { run: PartialRunStatus }) {
  const text = partialStatusText(run);
  return text ? <Badge variant="outline" className="max-w-full whitespace-normal" data-partial-badge><span aria-hidden="true">◐ </span>{text}</Badge> : null;
}
export function ProviderSkipNotices({ skips, short = false }: { skips?: readonly ProviderSkip[]; short?: boolean }) {
  if (!skips?.length) return null;
  return <div data-provider-skips>{skips.map(skip => <p key={skip.provider}><span aria-hidden="true">⚠ </span>{providerName(skip.provider)} skipped after {skip.after_failures} failures{!short && ' in a row — provider may be down'}</p>)}</div>;
}
