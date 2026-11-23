export type Mode = 'dataset' | 'upload';
export type CodedSpan = { start_turn: number; end_turn: number } | { start_ms: number; end_ms: number };
export interface EngineOption { id: string; label: string; engine: string; config?: string; prod: boolean; version?: string }
export interface Options {
  engines: EngineOption[];
  presets: { name: string; prod: boolean; models: Record<string, string> }[];
  defaults: Record<Mode, { engines: string[]; presets: string[] }>;
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
  presets: string[];
  repeats: 1 | 3;
  change_goal?: string;
  language?: string;
  coded_span?: CodedSpan;
}
export interface EvalApi {
  me(): Promise<unknown>;
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
