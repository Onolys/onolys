import { useState } from 'react';
import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@onolys/ui';
import type { RunSummary } from './api';

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
export function RunConfigDialog({ run, onClose }: { run: RunSummary | null; onClose: () => void }) {
  const [status, setStatus] = useState('');
  const json = run ? JSON.stringify(savedConfiguration(run), null, 2) : '';
  return <Dialog open={run !== null} onOpenChange={open => { if (!open) { setStatus(''); onClose(); } }}>
    <DialogContent className="eval-config-dialog flex w-[90vw] max-w-[52rem] flex-col sm:max-w-[52rem]">
      <DialogHeader><DialogTitle>Saved configuration and versions</DialogTitle><DialogDescription>Configuration and provenance saved with this run.</DialogDescription></DialogHeader>
      <div className="eval-config-json" role="textbox" aria-readonly="true" aria-multiline="true" tabIndex={0} aria-label="Saved configuration JSON"><pre>{json}</pre></div>
      <DialogFooter><span role="status">{status}</span><Button onClick={() => {
        void Promise.resolve().then(() => navigator.clipboard.writeText(json)).then(() => setStatus('Copied.')).catch(() => setStatus('Could not copy. Select the JSON to copy it manually.'));
      }}>Copy</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
