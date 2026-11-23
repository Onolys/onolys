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
