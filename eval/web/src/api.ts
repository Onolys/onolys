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
export type SourceMedia = 'audio' | 'video' | 'transcript';
export type TranscriptOrigin = 'human' | 'auto_captions' | 'translated' | 'stt_ours';
export interface DatasetMetadata {
  dataset_id: string; title: string;
  source_media?: SourceMedia[]; transcript_origin?: TranscriptOrigin; labels_summary?: string; miti_version?: string | null; label_scheme?: string; language?: string;
}
export interface Dataset extends DatasetMetadata { sessions: { session_id: string; title: string; has_gold?: boolean; coded_span?: CodedSpan }[] }
export interface Upload {
  upload_id: string;
  status: 'awaiting_upload' | 'ready' | 'awaiting_speakers' | 'transcribing' | 'failed';
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
 run_id: string; status: RunStatus; created_at: string; cancel_requested?: boolean;
 total_units: number; completed_units: number; done_units: number; failed_units: number; cancelled_units: number;
 usage: { input_tokens: number; output_tokens: number; cost_usd?: number | null; calls?: number };
 cost_usd_est: number | null; unpriced_units: number;
 engine_versions: Record<string, string>; engine_git_sha: Record<string, string> | string; resolved_presets: Record<string, unknown>;
 resolved_combos?: Record<string, unknown>; base_preset?: string;
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
export interface CompareCell {
 engine: string; combo_key: string; label: string; n: number; failed: number; error_code: string | null; unit_ids: string[];
 values: Record<string, { mean: number | null; min: number | null; max: number | null; n: number }>;
 diff?: Record<string, number | null>;
 error: Record<string, ErrorMetric> | null;
}
export interface CompareAggregate {
 engine: string; combo_key: string; label: string; n: number; failed: number;
 within_1: Record<string, { n: number; total: number; fraction: number | null }>;
 usage: { input_tokens: number; output_tokens: number; calls: number }; cost_usd_est: number | null; metrics: Aggregate;
}
export interface Compare {
 has_human: boolean; metrics: { id: string; group: 'counts' | 'globals' | 'summaries'; label: string }[];
 sessions: { session_id: string; human: Record<string, number | null> | null; quality_label?: 'high' | 'low' | null; cells: CompareCell[] }[];
 aggregates: CompareAggregate[]; notes: string[];
}
export interface RunDetail extends RunSummary { units: RunUnit[]; compare: Compare }
export type RunSelection = Pick<RunInput, 'engines' | 'selection' | 'repeats'>;
export interface EvalApi {
  me(): Promise<unknown>;
  runs(signal?: AbortSignal, cursor?: string): Promise<{ runs: RunSummary[]; next_cursor?: string | null }>;
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
const text = (value: unknown) => typeof value === 'string' && value.trim() ? value : undefined;
/** Message from an error body: `{error:{message}}`, FastAPI `{detail: str}` or `{detail:{message}}`; a list `detail` (422) maps to a fixed text because it echoes request input. */
export function errorText(body: unknown, status: number): string {
  const b = (body && typeof body === 'object' ? body : {}) as { error?: { message?: unknown }; detail?: unknown };
  const detail = b.detail;
  const message = text(b.error?.message) ?? text(detail) ?? (detail && typeof detail === 'object' && !Array.isArray(detail) ? text((detail as { message?: unknown }).message) : undefined);
  if (message) return message;
  if (Array.isArray(detail)) return 'Some values were not accepted. Check the form and try again.';
  return `Request failed (${status}). Please try again.`;
}
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) { super(message); this.name = 'ApiError'; this.status = status; }
}
export function createEvalApi(base: string, fetcher: typeof fetch, storageFetch: typeof fetch = (input, init) => fetch(input, init)): EvalApi {
  // Only retain pending attempts for this form object. Completed attempts can be collected.
  const pending = new WeakMap<UploadInput, { upload_id: string; upload: { url: string; method: string; headers: Record<string, string> }; written: boolean }>();
  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetcher(`${base.replace(/\/$/, '')}/v1${path}`, init);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(errorText(body, response.status), response.status);
    }
    return response.json() as Promise<T>;
  };
  const json = (value: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
  const id = encodeURIComponent;
  return {
    me: () => request('/me'),
    runs: (signal, cursor) => request(`/runs${cursor ? `?cursor=${id(cursor)}` : ''}`, { signal }),
    run: (runId, signal) => request(`/runs/${id(runId)}`, { signal }),
    output: (runId, unitId, signal) => request(`/runs/${id(runId)}/units/${id(unitId)}/output`, { signal }),
    cancel: runId => request(`/runs/${id(runId)}/cancel`, json({})),
    rerun: (runId, selection) => request(`/runs/${id(runId)}/rerun`, json(selection)),
    options: (mode, uploadId) => request(`/options?mode=${mode}${uploadId ? `&upload_id=${id(uploadId)}` : ''}`),
    datasets: () => request('/datasets'),
    dataset: datasetId => request(`/datasets/${id(datasetId)}`),
    upload: async input => {
      const multipart = () => {
        const body = new FormData();
        body.set('file', input.file);
        if (input.gold) body.set('gold', input.gold);
        body.set('change_goal', input.change_goal); body.set('language', input.language);
        if (input.coded_span) body.set('coded_span', JSON.stringify(input.coded_span));
        return request<Upload>('/uploads', { method: 'POST', body });
      };
      const audio = /\.(mp3|wav|m4a|webm|ogg)$/i.test(input.file.name);
      if (audio && input.file.size > 300 * 1024 * 1024) throw new Error('Recordings must be at most 300 MiB.');
      if (audio) {
        const legacySize = input.file.size <= 25 * 1024 * 1024;
        let saved = pending.get(input);
        if (!saved) {
          if (input.gold && input.gold.size > 1024 * 1024) throw new Error('Gold file must be at most 1 MiB.');
          let gold: unknown;
          try { gold = input.gold ? JSON.parse(await input.gold.text()) : undefined; }
          catch { throw new Error('Gold file must contain valid JSON.'); }
          const started = await request<{ upload_id: string; upload: { url: string; method: string; headers: Record<string, string> } }>('/uploads/audio', json({
            filename: input.file.name, content_type: input.file.type, size: input.file.size,
            change_goal: input.change_goal, language: input.language, coded_span: input.coded_span, ...(gold === undefined ? {} : { gold }),
          })).catch(error => {
            if (legacySize && error instanceof ApiError && error.status >= 500) return null;
            throw error;
          });
          if (!started) return multipart();
          saved = { ...started, written: false }; pending.set(input, saved);
        }
        if (!saved.written) {
          let response: Response;
          try {
            response = await storageFetch(saved.upload.url, { method: saved.upload.method, headers: saved.upload.headers, body: input.file, credentials: 'omit' });
          } catch {
            // No completion has been attempted, so this cannot queue a second
            // transcription. A PUT whose response was lost can leave unused bytes.
            if (legacySize) { pending.delete(input); return multipart(); }
            throw new Error('Recording upload could not connect. Check your connection and storage CORS configuration, then retry.');
          }
          // A lost PUT response may already have created the object. The server checks
          // the object before completing; the signed precondition prevents overwrites.
          if (!response.ok && response.status !== 412) {
            if (response.status === 403) pending.delete(input);
            throw new Error(response.status === 403 ? 'Recording upload permission expired or was denied. Retry to prepare a new upload.' : `Recording upload failed (${response.status}). Retry the upload.`);
          }
          saved.written = true;
        }
        try {
          const completed = await request<Upload>(`/uploads/${id(saved.upload_id)}/complete`, json({}));
          pending.delete(input); return completed;
        } catch (error) {
          if (error instanceof ApiError && (error.status === 409 || error.status === 422)) pending.delete(input);
          throw error;
        }
      }
      return multipart();
    },
    getUpload: (uploadId, signal) => request(`/uploads/${id(uploadId)}`, { signal }),
    speakers: (uploadId, speaker) => request(`/uploads/${id(uploadId)}/speakers`, json({ clinician_speaker: speaker })),
    start: input => request('/runs', json(input)),
  };
}
