import { createRoot } from 'react-dom/client';
import { createFakeAuthService } from '@prod-auth/fakeService';
import { Root } from './Root';
import overview from './compare/fixtures/overview.json';
import analysis from './compare/fixtures/analysis.json';
import deep from './compare/fixtures/deepDive.json';
import lines from './compare/fixtures/lines.json';

const tiers = [{ id: 'claude-sonnet-5-5', efforts: ['low', 'high'], default_effort: 'low' }, { id: 'claude-haiku-5', efforts: ['low'], default_effort: 'low' }];
const options = {
  engines: [{ id: 'human', engine: 'human', label: 'Human score', prod: false }, { id: 'miti', engine: 'miti', label: 'MITI lean (prod)', prod: true }, { id: 'oneshot:miti', engine: 'oneshot', config: 'miti', label: 'One-shot · MITI', prod: false }],
  models: [{ id: 'claude', label: 'Claude', context_tokens: 1000, max_output_tokens: 100, tiers }, { id: 'gemini', label: 'Gemini', context_tokens: 1000, max_output_tokens: 100, tiers: [{ id: 'gemini-pro', efforts: ['low', 'high'], default_effort: 'low' }] }],
  defaults: { dataset: { engines: ['human', 'miti'], selection: { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] }, label: 'Claude / sonnet / low (prod)' }, upload: { engines: ['miti'], selection: { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] }, label: 'x' } },
};
const base = { selection: { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] }, combos: null, legacy_selection: false, combo_keys: [], combo_labels: {}, engines: ['miti'], repeats: 1, input: { dataset_id: 'sample', session_ids: ['s1', 's2'] }, usage: { input_tokens: 1000, output_tokens: 500, cost_usd: 0.12 }, cost_usd_est: 0.12, unpriced_units: 0, engine_versions: {}, engine_git_sha: {}, resolved_presets: {}, cancelled_units: 0, failed_units: 0 };
const runs = [
  { ...base, run_id: 'r1', name: 'Sample sweep', status: 'running', created_at: '2026-11-26T05:00:00Z', total_units: 8, done_units: 3, completed_units: 3, running_units: 2, queued_units: 3 },
  { ...base, run_id: 'r2', name: 'Older run', status: 'done', created_at: '2026-11-25T05:00:00Z', total_units: 4, done_units: 4, completed_units: 4 },
];
const units = [
  { unit_id: 'u1', session_id: 's1', engine: 'miti', repeat: 0, status: 'running', stage: 'coding (chunk 2 of 5)' },
  { unit_id: 'u2', session_id: 's2', engine: 'miti', repeat: 0, status: 'done' },
  { unit_id: 'u3', session_id: 's2', engine: 'oneshot:miti', repeat: 0, status: 'waiting' },
];
const j = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } });
const baseFetch = async (input: RequestInfo | URL) => {
  const p = new URL(String(input), location.href); const path = p.pathname.replace(/^.*\/v1/, '');
  if (path === '/me') return j({});
  if (path === '/options') return j(options);
  if (path === '/datasets') return j({ datasets: [{ dataset_id: 'sample', title: 'Sample dataset', source_media: ['video', 'transcript'], transcript_origin: 'human', labels_summary: 'MITI counts', miti_version: '4.2.1' }] });
  if (path === '/datasets/sample') return j({ dataset_id: 'sample', title: 'Sample dataset', sessions: [{ session_id: 's1', title: 'First' }, { session_id: 's2', title: 'Second' }] });
  if (path === '/runs') return j({ runs });
  if (path.endsWith('/output')) return j({ globals: { empathy: 4 }, counts: { reflections: 3 }, note: 'sample output' });
  if (path.startsWith('/runs/')) return j({ ...runs[0], units });
  if (path.includes('/compare/overview')) return j(overview);
  if (path.includes('/compare/')) { const k = path.split('/compare/')[1]; return j(k.startsWith('analysis') ? analysis : k.startsWith('deep') ? deep : lines); }
  return j({}, 404);
};
const svc = createFakeAuthService(); svc.signedInAs('a@example.com', { verified: true });
createRoot(document.getElementById('root')!).render(<Root service={svc} baseFetch={baseFetch as typeof fetch} />);
