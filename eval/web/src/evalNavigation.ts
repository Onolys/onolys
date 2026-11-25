import type { RunSummary } from './api';
import { buildCompareUrl, type CompareUrlState } from './compare/compareUrl';

/** Query navigation shared by run links and Compare drill-downs. */
export function navigateEval(state: CompareUrlState, saved?: RunSummary) {
  const url = new URL(window.location.href);
  url.search = buildCompareUrl(state, url.searchParams);
  window.history.pushState(saved ? { initialRun: saved } : {}, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
