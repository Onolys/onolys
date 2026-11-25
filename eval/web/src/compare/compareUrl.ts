export type CompareTab = 'overview' | 'deep' | 'more' | 'lines';
export interface CompareUrlState {
 run?: string; view: 'run' | 'compare' | 'history' | 'new'; tab?: CompareTab;
 combos?: string[]; combo?: string; code?: string; metric?: string; session?: string; turn?: string; only?: string;
}
const keys = ['run', 'view', 'tab', 'combos', 'combo', 'code', 'metric', 'session', 'turn', 'only'] as const;
export function parseCompareUrl(search: string | URLSearchParams): CompareUrlState & { tab: CompareTab; combos: string[] } {
 const params = new URLSearchParams(search);
 const run = params.get('run') || undefined, combo = params.get('combo') || undefined;
 const tab = params.get('tab');
 return {
  run, view: run ? params.get('view') === 'compare' ? 'compare' : 'run' : params.get('view') === 'history' ? 'history' : 'new',
  tab: tab === 'deep' || tab === 'more' || tab === 'lines' ? tab : 'overview',
  combos: [...new Set((params.get('combos') || combo || '').split(',').filter(Boolean))],
  ...Object.fromEntries(['combo', 'code', 'metric', 'session', 'turn', 'only'].map(key => [key, params.get(key) || undefined])),
 };
}
/** Builds a query string, retaining unrelated query parameters and clearing stale navigation. */
export function buildCompareUrl(state: CompareUrlState, base: string | URLSearchParams = ''): string {
 const params = new URLSearchParams(base);
 keys.forEach(key => params.delete(key));
 if (state.run) params.set('run', state.run);
 if (state.view === 'compare' && state.run) {
  params.set('view', 'compare'); params.set('tab', state.tab ?? 'overview');
  if (state.combos?.length) params.set('combos', [...new Set(state.combos)].join(','));
  for (const key of ['combo', 'code', 'metric', 'session', 'turn', 'only'] as const) if (state[key]) params.set(key, state[key]);
 } else if (state.view === 'history') params.set('view', 'history');
 const query = params.toString(); return query ? `?${query}` : '';
}
