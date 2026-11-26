import type { RefObject } from 'react';
import type { RunSummary } from './api';
import { JsonDialog } from './JsonViewer';

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
export function RunConfigDialog({ run, onClose, returnFocus }: { run: RunSummary | null; onClose: () => void; returnFocus: RefObject<HTMLElement | null> }) {
  return <JsonDialog open={run !== null} onOpenChange={open => { if (!open) onClose(); }} title="Saved configuration and versions"
    description="Configuration and provenance saved with this run." value={run ? savedConfiguration(run) : undefined}
    onCloseAutoFocus={event => { event.preventDefault(); returnFocus.current?.focus(); }} />;
}
