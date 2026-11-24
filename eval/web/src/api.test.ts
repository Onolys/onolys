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
