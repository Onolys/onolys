import { Copy } from 'lucide-react';
import { useState, type RefObject } from 'react';
import { Button } from '@onolys/ui';
import type { RunSummary } from './api';
import { prettyJson } from './JsonViewer';
import { AppDialog } from './ui/AppDialog';
import { Chip } from './ui/Chip';
import { ComboTag } from './ui/ComboTag';
import { Disclosure } from './ui/Disclosure';
import { StatTile } from './ui/StatTile';

/** The saved public configuration, without unit output or private storage references. */
export function savedConfiguration(run: RunSummary) {
  return {
    name: run.name, description: run.description, input: run.input,
    change_goal: run.change_goal, language: run.language, coded_span: run.coded_span,
    engines: run.engines, selection: run.selection, combos: run.combos,
    combo_keys: run.combo_keys, combo_labels: run.combo_labels, legacy_selection: run.legacy_selection,
    presets: run.presets, repeats: run.repeats, engine_versions: run.engine_versions,
    engine_git_sha: run.engine_git_sha, base_preset: run.base_preset,
    resolved_combos: run.resolved_combos, resolved_presets: run.resolved_presets,
  };
}
const dash = '—';
const versions = (run: RunSummary) => {
  const sha = typeof run.engine_git_sha === 'string' ? {} : run.engine_git_sha ?? {};
  const out = Object.entries(run.engine_versions ?? {}).map(([engine, v]) => `${engine} ${v}${sha[engine] ? ` (${sha[engine]})` : ''}`);
  return out.length ? out.join(' · ') : typeof run.engine_git_sha === 'string' && run.engine_git_sha ? run.engine_git_sha : dash;
};

function ComboList({ run }: { run: RunSummary }) {
  const engines = run.engines.filter(engine => engine !== 'human');
  const rows = run.combos?.length
    ? run.combos.map(c => ({ key: `${c.model}/${c.tier}/${c.effort}`, engines, model: c.model, tier: c.tier, effort: c.effort }))
    : run.combo_keys.map(key => ({ key, engines: [] as string[], model: run.combo_labels?.[key] ?? key, tier: '', effort: '' }));
  if (!rows.length) return null;
  return <div><h3 className="ui-config-heading">Combos</h3><ul className="ui-config-combos">{rows.map((r, i) => <li key={`${r.key}-${i}`}>
    <ComboTag index={i} />{r.engines.map(engine => <Chip key={engine} mono>{engine}</Chip>)}<strong>{r.model}</strong>
    {r.tier && <Chip tone="info">{r.tier}</Chip>}{r.effort && <Chip tone="info">{r.effort}</Chip>}
  </li>)}</ul></div>;
}

/** Shared "Config" popup (run page, History): key-fact tiles, combo list, raw JSON behind a disclosure, Copy. */
export function RunConfigDialog({ run, onClose, returnFocus }: { run: RunSummary | null; onClose: () => void; returnFocus: RefObject<HTMLElement | null> }) {
  const [status, setStatus] = useState('');
  const json = run ? prettyJson(savedConfiguration(run)) : '';
  const copy = () => { void Promise.resolve().then(() => navigator.clipboard.writeText(json)).then(() => setStatus('Copied.')).catch(() => setStatus('Could not copy. Expand the raw JSON and select it to copy manually.')); };
  const onOpenChange = (open: boolean) => { if (!open) { setStatus(''); onClose(); } };
  return <AppDialog open={run !== null} onOpenChange={onOpenChange} title="Run configuration" returnFocus={returnFocus}
    description={run ? <>Saved with run <code>{run.run_id}</code></> : undefined}
    footer={<><span role="status" className="ui-config-status">{status}</span><Button type="button" variant="outline" onClick={copy}><Copy aria-hidden="true" />Copy</Button></>}>
    {run && <div className="ui-config">
      <div className="ui-config-tiles">
        <StatTile label="Dataset" value={'dataset_id' in run.input ? run.input.dataset_id : 'Uploaded recording'} />
        <StatTile label="Sessions" value={'session_ids' in run.input ? run.input.session_ids.join(', ') || dash : dash} />
        <StatTile label="Attempts / cell" value={run.repeats} />
        <StatTile label="Change goal" value={run.change_goal || dash} />
        <StatTile label="Language" value={run.language || dash} />
        <StatTile label="Engine versions" value={versions(run)} />
      </div>
      <ComboList run={run} />
      <Disclosure label="Show raw JSON"><div className="eval-config-json" role="textbox" aria-readonly="true" aria-multiline="true" tabIndex={0} aria-label="Run configuration (JSON)"><pre>{json}</pre></div></Disclosure>
    </div>}
  </AppDialog>;
}
