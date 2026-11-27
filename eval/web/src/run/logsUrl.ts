/** Cloud Logging deep links for eval units. Verified in eval/backend: a unit's `unit_id` is its RunDoc id (`cell["run_id"]`, passed to `create_run(run_id=...)`), i.e. the `jsonPayload.run_id` the worker logs. The eval group id is NOT in worker logs. Units with no RunDoc yet carry placeholder ids (`cell-…`, `human-…`) that never appear in logs, so they are skipped. */
export const LOGS_PROJECT = 'onolys-eval';
export const LOGS_SERVICE = 'onolys-worker-eval';
export const LOGS_DURATION = 'P14D';
/** Max run ids in one run-level query, to stay under URL limits. */
export const MAX_LOGS_IDS = 40;

const BASE = 'https://console.cloud.google.com/logs/query';
const quote = (id: string) => `"${id.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
/** encodeURIComponent leaves ( ) ' ! * ~ raw; the Cloud Console treats parentheses in the URL as its own state syntax and drops the query, so encode them too. */
const enc = (s: string) => encodeURIComponent(s).replace(/[!'()*~]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
const url = (filter: string) => `${BASE};query=${enc(`resource.labels.service_name=${quote(LOGS_SERVICE)} AND ${filter}`)};duration=${LOGS_DURATION}?project=${LOGS_PROJECT}`;

export const isWorkerRunId = (id: string | null | undefined): id is string => !!id && !id.startsWith('cell-') && !id.startsWith('human-');

/** Logs link for one unit run id, or null when there is none. */
export function unitLogsUrl(runId: string | null | undefined): string | null {
  return isWorkerRunId(runId) ? url(`jsonPayload.run_id=${quote(runId)}`) : null;
}

export interface RunLogsLink { url: string; truncated: boolean; used: number; total: number }

/** Logs link for a set of unit run ids (OR, first 40; `truncated` says ids were dropped). Null when no usable ids. */
export function runLogsUrl(runIds: readonly (string | null | undefined)[]): RunLogsLink | null {
  const all = [...new Set(runIds.filter(isWorkerRunId))];
  if (!all.length) return null;
  const used = all.slice(0, MAX_LOGS_IDS);
  const filter = used.length === 1 ? `jsonPayload.run_id=${quote(used[0])}` : `jsonPayload.run_id=(${used.map(quote).join(' OR ')})`;
  return { url: url(filter), truncated: all.length > used.length, used: used.length, total: all.length };
}
