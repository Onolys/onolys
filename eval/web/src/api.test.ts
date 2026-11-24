import { describe, expect, it, vi } from 'vitest';
import { createEvalApi } from './api';

describe('eval API', () => {
  it('sends multipart upload fields without a JSON content type and encodes IDs', async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response('{}'));
    const api = createEvalApi('https://eval-api/', fetcher);
    const file = new File(['input'], 'input.txt'); const gold = new File(['gold'], 'gold.json');
    await api.upload({ file, gold, change_goal: 'Goal', language: 'en', coded_span: { start_turn: 0, end_turn: 5 } });
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('https://eval-api/v1/uploads'); expect(init?.headers).toBeUndefined();
    const body = init?.body;
    if (!(body instanceof FormData)) throw new Error('Expected multipart form data');
    expect(body.get('file')).toBe(file); expect(body.get('gold')).toBe(gold);
    expect(body.get('change_goal')).toBe('Goal'); expect(body.get('language')).toBe('en');
    expect(JSON.parse(String(body.get('coded_span')))).toEqual({ start_turn: 0, end_turn: 5 });
    await api.speakers('a/b', 'Real label');
    expect(fetcher.mock.calls[1][0]).toBe('https://eval-api/v1/uploads/a%2Fb/speakers');
    expect(JSON.parse(String(fetcher.mock.calls[1][1]?.body))).toEqual({ clinician_speaker: 'Real label' });
  });
  it('rejects unsuccessful responses with a usable message', async () => {
    const api = createEvalApi('', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'bad', message: 'Choose a smaller span' } }), { status: 422 })));
    await expect(api.datasets()).rejects.toThrow('Choose a smaller span');
  });
});

describe('eval API errors (FastAPI shapes)', () => {
  const failing = (status: number, body: unknown) => createEvalApi('', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
  it('reads a string detail', async () => {
    await expect(failing(422, { detail: 'Human requires gold' }).datasets()).rejects.toThrow('Human requires gold');
  });
  it('reads a {code, message} detail object', async () => {
    await expect(failing(400, { detail: { code: 'bad_file', message: 'Unsupported audio type' } }).datasets()).rejects.toThrow('Unsupported audio type');
  });
  it('maps a list detail (422) to a fixed message that never echoes request input', async () => {
    const body = { detail: [{ type: 'string_too_long', loc: ['body', 'change_goal'], msg: 'String should have at most 4000 characters', input: 'SECRET-GOAL-TEXT' }] };
    const error = await failing(422, body).datasets().then(() => new Error('resolved'), (e: unknown) => e as Error);
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe('Some values were not accepted. Check the form and try again.');
    expect(error.message).not.toContain('SECRET-GOAL-TEXT');
  });
  it('falls back to a generic message with the status', async () => {
    await expect(failing(502, { other: 1 }).datasets()).rejects.toThrow('Request failed (502). Please try again.');
  });
});

it('uses encoded saved-run, cancel, output and rerun endpoints with abort signals', async () => {
  const fetcher = vi.fn<typeof fetch>(async () => new Response('{}'));
  const api = createEvalApi('', fetcher); const signal = new AbortController().signal;
  await api.runs(signal); await api.run('a/b', signal); await api.output('a/b', 'u/v', signal); await api.cancel('a/b');
  await api.rerun('a/b', { engines: ['miti'], selection: { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] }, repeats: 3 });
  expect(fetcher.mock.calls.map(call => call[0])).toEqual(['/v1/runs', '/v1/runs/a%2Fb', '/v1/runs/a%2Fb/units/u%2Fv/output', '/v1/runs/a%2Fb/cancel', '/v1/runs/a%2Fb/rerun']);
  expect(fetcher.mock.calls[2][1]?.signal).toBe(signal);
  expect(JSON.parse(String(fetcher.mock.calls[4][1]?.body))).toEqual({ engines: ['miti'], selection: { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] }, repeats: 3 });
});

it('retains HTTP status and pages history using the opaque cursor', async () => {
  const fetcher = vi.fn<typeof fetch>(async () => new Response('{}'));
  const api = createEvalApi('', fetcher); const signal = new AbortController().signal;
  await api.runs(signal, 'opaque/+=');
  expect(fetcher.mock.calls[0][0]).toBe('/v1/runs?cursor=opaque%2F%2B%3D');
  const missing = createEvalApi('', vi.fn().mockResolvedValue(new Response('{}', { status: 404 })));
  await expect(missing.run('gone')).rejects.toMatchObject({ status: 404 });
});
it('uploads large audio raw without auth and passes all metadata through the signed start route', async () => {
  const signed = { url: 'https://storage.googleapis.com/private/input', method: 'PUT', headers: { 'Content-Type': 'audio/wav', 'x-goog-if-generation-match': '0' } };
  const auth = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify({ upload_id: 'large/id', status: 'awaiting_upload', upload: signed }))).mockResolvedValueOnce(new Response(JSON.stringify({ upload_id: 'large/id', status: 'transcribing' })));
  const raw = vi.fn<typeof fetch>().mockResolvedValue(new Response(null));
  const api = createEvalApi('', auth, raw);
  const file = new File(['audio'], 'session.wav', { type: 'audio/wav' }); Object.defineProperty(file, 'size', { value: 25 * 1024 * 1024 + 1 });
  const gold = new File(['{"test":true}'], 'gold.json');
  Object.defineProperty(gold, 'text', { value: async () => '{"test":true}' });
  const input = { file, gold, change_goal: 'Goal', language: 'en', coded_span: { start_turn: 0, end_turn: 5 } };
  expect(await api.upload(input)).toMatchObject({ status: 'transcribing' });
  expect(auth.mock.calls.map(c => c[0])).toEqual(['/v1/uploads/audio', '/v1/uploads/large%2Fid/complete']);
  expect(JSON.parse(String(auth.mock.calls[0][1]?.body))).toEqual({ filename: 'session.wav', content_type: 'audio/wav', size: file.size, gold: { test: true }, change_goal: 'Goal', language: 'en', coded_span: input.coded_span });
  expect(raw).toHaveBeenCalledExactlyOnceWith(signed.url, { method: 'PUT', headers: signed.headers, body: file, credentials: 'omit' });
});
it('retries completion without reuploading a successfully written recording', async () => {
  const auth = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify({ upload_id: 'u', upload: { url: 'https://storage.googleapis.com/b/o', method: 'PUT', headers: {} } }))).mockResolvedValueOnce(new Response('{}', { status: 503 })).mockResolvedValueOnce(new Response('{"status":"transcribing"}'));
  const raw = vi.fn<typeof fetch>().mockResolvedValue(new Response(null)); const api = createEvalApi('', auth, raw);
  const file = new File(['a'], 'x.mp3'); Object.defineProperty(file, 'size', { value: 26 * 1024 * 1024 });
  const input = { file, change_goal: 'g', language: 'en' };
  await expect(api.upload(input)).rejects.toThrow(); await api.upload(input);
  expect(raw).toHaveBeenCalledTimes(1); expect(auth.mock.calls.map(c => c[0])).toEqual(['/v1/uploads/audio', '/v1/uploads/u/complete', '/v1/uploads/u/complete']);
});

it('keeps audio at the multipart cap on the ordinary route and rejects over 300 MiB before starting', async () => {
  const auth = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}')); const raw = vi.fn<typeof fetch>();
  const api = createEvalApi('', auth, raw); const file = new File(['audio'], 'x.mp3');
  Object.defineProperty(file, 'size', { value: 25 * 1024 * 1024, configurable: true });
  await api.upload({ file, change_goal: 'g', language: 'en' });
  expect(auth.mock.calls[0][0]).toBe('/v1/uploads'); expect(auth.mock.calls[0][1]?.body).toBeInstanceOf(FormData);
  Object.defineProperty(file, 'size', { value: 300 * 1024 * 1024 + 1 });
  await expect(api.upload({ file, change_goal: 'g', language: 'en' })).rejects.toThrow('300 MiB');
  expect(auth).toHaveBeenCalledTimes(1); expect(raw).not.toHaveBeenCalled();
});
it('handles a lost PUT response using the write-once conflict then completion', async () => {
  const auth = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify({ upload_id: 'u', upload: { url: 'https://storage.googleapis.com/b/o', method: 'PUT', headers: {} } }))).mockResolvedValueOnce(new Response('{"status":"transcribing"}'));
  const raw = vi.fn<typeof fetch>().mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce(new Response(null, { status: 412 }));
  const api = createEvalApi('', auth, raw); const file = new File(['audio'], 'x.mp3'); Object.defineProperty(file, 'size', { value: 300 * 1024 * 1024 });
  const input = { file, change_goal: 'g', language: 'en' };
  await expect(api.upload(input)).rejects.toThrow('CORS');
  expect(auth).toHaveBeenCalledTimes(1);
  expect(await api.upload(input)).toMatchObject({ status: 'transcribing' });
  expect(auth.mock.calls.map(c => c[0])).toEqual(['/v1/uploads/audio', '/v1/uploads/u/complete']); expect(raw).toHaveBeenCalledTimes(2);
});
it('restarts expired signed PUT attempts without sending storage failures through the auth gate', async () => {
  const target = { upload_id: 'u', upload: { url: 'https://storage.googleapis.com/b/o', method: 'PUT', headers: {} } };
  const auth = vi.fn<typeof fetch>().mockImplementation(async () => new Response(JSON.stringify(target)));
  const raw = vi.fn<typeof fetch>().mockImplementation(async () => new Response(null, { status: 403 }));
  const api = createEvalApi('', auth, raw); const file = new File(['a'], 'x.mp3'); Object.defineProperty(file, 'size', { value: 26 * 1024 * 1024 });
  const input = { file, change_goal: 'g', language: 'en' };
  await expect(api.upload(input)).rejects.toThrow('permission expired'); await expect(api.upload(input)).rejects.toThrow('permission expired');
  expect(auth.mock.calls.map(c => c[0])).toEqual(['/v1/uploads/audio', '/v1/uploads/audio']);
});
