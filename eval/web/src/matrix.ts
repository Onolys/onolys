import type { Combo, ModelOption, Selection } from './api';

/** Client mirror of eval/backend matrix.py (validate_selection / plan count). Server stays authoritative;
 * both are tested against eval/fixtures/selection_cases.json. */
export const MAX_UNITS = 499;
export type ModelMap = Record<string, Record<string, string[]>>;
export const tooLargeMessage = (count: number) => `Run has ${count} units; the maximum is ${MAX_UNITS}. Remove sessions, combos or repeats.`;
export const comboKey = (c: Combo) => `${c.model}/${c.tier}/${c.effort}`;
export const modelMap = (models: ModelOption[]): ModelMap => Object.fromEntries(models.map(m => [m.id, Object.fromEntries(m.tiers.map(t => [t.id, t.efforts]))]));

export type Validation = { combos: Combo[]; dropped: Combo[]; error?: undefined } | { error: string };

export function validateSelection(models: ModelMap, selection: Selection, needsCombos = true): Validation {
  const { models: selModels, tiers: selTiers, efforts: selEfforts } = selection;
  const owner: Record<string, string> = {};
  for (const [m, tiers] of Object.entries(models)) for (const t of Object.keys(tiers)) owner[t] = m;
  const known = new Set(Object.values(models).flatMap(tiers => Object.values(tiers).flat()));
  for (const m of selModels) if (!(m in models)) return { error: `Unknown model '${m}'.` };
  for (const t of selTiers) if (!(t in owner)) return { error: `Unknown tier '${t}'.` };
  for (const e of selEfforts) if (!known.has(e)) return { error: `Unknown effort '${e}'.` };
  for (const m of selModels) if (!selTiers.some(t => owner[t] === m)) return { error: `Model '${m}' has no selected tier.` };
  for (const t of selTiers) if (!selModels.includes(owner[t])) return { error: `Tier '${t}' belongs to model '${owner[t]}', which is not selected.` };
  if (selTiers.length) for (const e of selEfforts) if (!selTiers.some(t => models[owner[t]][t].includes(e))) return { error: `Effort '${e}' is not supported by any selected tier.` };
  const combos: Combo[] = [], dropped: Combo[] = [];
  for (const m of selModels) for (const t of selTiers) {
    if (owner[t] !== m) continue;
    for (const e of selEfforts) (models[m][t].includes(e) ? combos : dropped).push({ model: m, tier: t, effort: e });
  }
  if (needsCombos && !combos.length) return { error: 'Selection has no valid model, tier and effort combination.' };
  return { combos, dropped };
}

export interface Plan { units: number; human: number; engines: number; combos: number; sessions: number; repeats: number }
export function planCount(sessions: number, engines: string[], combos: number, repeats: number): Plan {
  const human = engines.includes('human') ? 1 : 0, ai = engines.filter(e => e !== 'human').length;
  return { units: sessions * (human + ai * combos * repeats), human, engines: ai, combos, sessions, repeats };
}
export const countText = (p: Plan) => `${p.units} units = ${p.sessions} sessions x (${p.human} human + ${p.engines} engines x ${p.combos} combos x ${p.repeats} repeats)`;
export const skippedText = (dropped: Combo[]) => dropped.map(c => `skipped: ${c.tier} has no ${c.effort}`);

/** Tiers offered for the selected models, and the union of their efforts (in catalog order). */
export const tiersFor = (models: ModelOption[], selected: string[]) => models.filter(m => selected.includes(m.id)).flatMap(m => m.tiers.map(t => ({ ...t, model: m.id })));
export const effortsFor = (models: ModelOption[], tiers: string[]) => {
  const out: string[] = [];
  for (const t of models.flatMap(m => m.tiers)) if (tiers.includes(t.id)) for (const e of t.efforts) if (!out.includes(e)) out.push(e);
  return out;
};
