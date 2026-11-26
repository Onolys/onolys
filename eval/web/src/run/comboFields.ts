import type { RunSummary } from '../api';

/** Model / tier / effort of a combo key or legacy preset, from saved combos or resolved presets. */
export function comboFields(run: RunSummary, preset?: string | null) {
  const index = preset ? run.combo_keys?.indexOf(preset) : -1;
  const combo = index >= 0 ? run.combos?.[index] : undefined;
  const resolved = (preset ? run.resolved_combos?.[preset] ?? run.resolved_presets?.[preset.replace(/^preset:/, '')] : undefined) as Record<string, unknown> | undefined;
  const string = (value: unknown) => typeof value === 'string' ? value : '';
  const legacyModels = preset && run.presets?.includes(preset.replace(/^preset:/, '')) ? [...new Set(Object.values(resolved ?? {}).filter(value => typeof value === 'string'))].join(', ') : '';
  return {
    model: combo?.model || string(resolved?.model) || string(resolved?.litellm_id) || legacyModels,
    tier: combo?.tier || string(resolved?.tier),
    effort: combo?.effort || string(resolved?.effort) || string(resolved?.reasoning_effort),
  };
}
