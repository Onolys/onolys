export type Mode = 'dataset' | 'upload';
export type CodedSpan = { start_turn: number; end_turn: number } | { start_ms: number; end_ms: number };
export interface EngineOption { id: string; label: string; engine: string; config?: string; prod: boolean; version?: string }
export interface Selection { models: string[]; tiers: string[]; efforts: string[] }
export interface Combo { model: string; tier: string; effort: string }
export interface ModelOption { id: string; label: string; context_tokens: number; max_output_tokens: number; tiers: { id: string; efforts: string[]; default_effort: string }[] }
export interface Options {
  engines: EngineOption[];
  models: ModelOption[];
  defaults: Record<Mode, { engines: string[]; selection: Selection; label: string }>;
}
export interface DatasetMetadata { dataset_id: string; title: string }
export interface Dataset extends DatasetMetadata { sessions: { session_id: string; title: string; has_gold?: boolean; coded_span?: CodedSpan }[] }
export interface Upload {
  upload_id: string;
  status: 'ready' | 'awaiting_speakers' | 'transcribing' | 'failed';
  has_gold: boolean;
  speakers: { speaker: string; samples: string[] }[];
  error?: { code: string; message: string };
}
export interface UploadInput { file: File; gold?: File; change_goal: string; language: string; coded_span?: CodedSpan }
export interface RunInput {
  input: { dataset_id: string; session_ids: string[] } | { upload_id: string };
  engines: string[];
  selection: Selection;
  repeats: 1 | 3;
  change_goal?: string;
  language?: string;
  coded_span?: CodedSpan;
}
export type RunStatus = 'queued' | 'running' | 'done' | 'partial' | 'failed' | 'cancelled';
export interface RunSummary extends Omit<RunInput, 'selection'> {
 selection: Selection | null; combos: Combo[] | null; legacy_selection: boolean; combo_keys: string[]; combo_labels: Record<string, string>; presets?: string[];
 run_id: string; status: RunStatus; created_at: string;
 total_units: number; completed_units: number; done_units: number; failed_units: number; cancelled_units: number;
 usage: { input_tokens: number; output_tokens: number; cost_usd?: number | null; calls?: number };
 cost_usd_est: number | null; unpriced_units: number;
 engine_versions: Record<string, string>; engine_git_sha: Record<string, string> | string; resolved_presets: Record<string, unknown>;
}
export interface RunUnit {
 unit_id: string; session_id: string; engine: string; preset?: string | null; repeat?: number | null;
 status: Exclude<RunStatus, 'partial'>; stage?: string; error?: { code: string; message?: string } | string; output?: unknown;
}
export interface ErrorMetric { mae: number | null; mean_bias: number | null; n: number }
export interface Aggregate {
 n: number; counts: Record<string, ErrorMetric>; summaries: Record<string, ErrorMetric>;
 globals: Record<string, ErrorMetric & { within_1: { n: number; total: number; fraction: number | null } }>;
}
export interface Compare {
 has_human: boolean; metrics: { id: string; group: 'counts' | 'globals' | 'summaries'; label: string }[];
 sessions: { session_id: string; human: Record<string, number | null> | null; cells: {
 engine: string; preset: string; n: number; failed: number; unit_ids: string[];
 values: Record<string, { mean: number | null; min: number | null; max: number | null; n: number }>;
 diff?: Record<string, number | null>;
 }[] }[];
 aggregates: { engine: string; preset: string; metrics: Aggregate }[]; notes: string[];
}
export interface RunDetail extends RunSummary { units: RunUnit[]; compare: Compare }
export type RunSelection = Pick<RunInput, 'engines' | 'selection' | 'repeats'>;
export interface EvalApi {
  me(): Promise<unknown>;
  runs(signal?: AbortSignal): Promise<{ runs: RunSummary[] }>;
  run(id: string, signal?: AbortSignal): Promise<RunDetail>;
  output(runId: string, unitId: string, signal?: AbortSignal): Promise<unknown>;
  cancel(id: string): Promise<{ run_id: string; status: RunStatus }>;
  rerun(id: string, selection: RunSelection): Promise<{ run_id: string; status: string }>;
  options(mode: Mode, uploadId?: string): Promise<Options>;
  datasets(): Promise<{ datasets: DatasetMetadata[] }>;
  dataset(id: string): Promise<Dataset>;
  upload(input: UploadInput): Promise<Upload>;
  getUpload(id: string, signal?: AbortSignal): Promise<Upload>;
  speakers(id: string, speaker: string): Promise<Upload>;
  start(input: RunInput): Promise<{ run_id: string; status: string }>;
}
export function createEvalApi(base: string, fetcher: typeof fetch): EvalApi {
  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetcher(`${base.replace(/\/$/, '')}/v1${path}`, init);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.error?.message || `Request failed (${response.status}). Please try again.`);
    }
    return response.json() as Promise<T>;
  };
  const json = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
  const id = encodeURIComponent;
  return {
    me: () => request('/me'),
    runs: signal => request('/runs', { signal }),
    run: (runId, signal) => request(`/runs/${id(runId)}`, { signal }),
    output: (runId, unitId, signal) => request(`/runs/${id(runId)}/units/${id(unitId)}/output`, { signal }),
    cancel: runId => request(`/runs/${id(runId)}/cancel`, json({})),
    rerun: (runId, selection) => request(`/runs/${id(runId)}/rerun`, json(selection)),
    options: (mode, uploadId) => request(`/options?mode=${mode}${uploadId ? `&upload_id=${id(uploadId)}` : ''}`),
    datasets: () => request('/datasets'),
    dataset: datasetId => request(`/datasets/${id(datasetId)}`),
    upload: input => {
      const body = new FormData();
      body.set('file', input.file);
      if (input.gold) body.set('gold', input.gold);
      body.set('change_goal', input.change_goal); body.set('language', input.language);
      if (input.coded_span) body.set('coded_span', JSON.stringify(input.coded_span));
      return request('/uploads', { method: 'POST', body });
    },
    getUpload: (uploadId, signal) => request(`/uploads/${id(uploadId)}`, { signal }),
    speakers: (uploadId, speaker) => request(`/uploads/${id(uploadId)}/speakers`, json({ clinician_speaker: speaker })),
    start: input => request('/runs', json(input)),
  };
}
