import type { CompareOverview } from './compareApi';

export interface FailedCombo { combo_key: string; code: string; runs: number; all: boolean }
/** Combos with failed runs and the first error code, from the payload's exclusions. `all` = every planned run failed. */
export function failedCombos(data: Pick<CompareOverview, 'excluded' | 'header'>): FailedCombo[] {
 const perCombo = data.header.sessions * data.header.repeats;
 const found = new Map<string, FailedCombo>();
 for (const item of data.excluded) {
  if (!item.combo_key || !item.reason.startsWith('failed:')) continue;
  const entry = found.get(item.combo_key) ?? { combo_key: item.combo_key, code: item.reason.slice('failed:'.length), runs: 0, all: false };
  entry.runs += 1; entry.all = entry.runs >= perCombo; found.set(item.combo_key, entry);
 }
 return [...found.values()];
}
