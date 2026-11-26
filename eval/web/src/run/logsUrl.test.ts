import { describe, expect, it } from 'vitest';
import { LOGS_DURATION, LOGS_PROJECT, LOGS_SERVICE, MAX_LOGS_IDS, isWorkerRunId, runLogsUrl, unitLogsUrl } from './logsUrl';

const base = 'https://console.cloud.google.com/logs/query;query=';
const tail = `;duration=${LOGS_DURATION}?project=${LOGS_PROJECT}`;
const q = (s: string) => encodeURIComponent(s);

describe('logsUrl', () => {
  it('constants', () => {
    expect([LOGS_PROJECT, LOGS_SERVICE, LOGS_DURATION, MAX_LOGS_IDS]).toEqual(['onolys-eval', 'onolys-worker-eval', 'P7D', 40]);
  });
  it('builds the exact URL for one unit', () => {
    expect(unitLogsUrl('abc123')).toBe(`${base}${q('resource.labels.service_name="onolys-worker-eval" AND jsonPayload.run_id="abc123"')}${tail}`);
    expect(unitLogsUrl('abc123')).toContain('%22abc123%22');
    expect(unitLogsUrl('abc123')).not.toMatch(/ /);
  });
  it('escapes quotes and backslashes inside ids', () => {
    expect(unitLogsUrl('a"b\\c')).toContain(q('jsonPayload.run_id="a\\"b\\\\c"'));
  });
  it('returns null for an empty or missing unit id', () => {
    expect(unitLogsUrl('')).toBeNull();
    expect(unitLogsUrl(undefined)).toBeNull();
    expect(unitLogsUrl(null)).toBeNull();
  });
  it('ORs several ids at run level', () => {
    const r = runLogsUrl(['a', 'b', 'c'])!;
    expect(r.url).toBe(`${base}${q('resource.labels.service_name="onolys-worker-eval" AND jsonPayload.run_id=("a" OR "b" OR "c")')}${tail}`);
    expect(r).toMatchObject({ truncated: false, used: 3, total: 3 });
  });
  it('uses the plain form for a single id', () => {
    expect(runLogsUrl(['a'])!.url).toBe(unitLogsUrl('a'));
  });
  it('caps at 40 ids and flags truncation', () => {
    const ids = Array.from({ length: 55 }, (_, i) => `id${i}`);
    const r = runLogsUrl(ids)!;
    expect(r).toMatchObject({ truncated: true, used: 40, total: 55 });
    expect(decodeURIComponent(r.url)).toContain('"id39"');
    expect(decodeURIComponent(r.url)).not.toContain('"id40"');
  });
  it('exactly 40 is not truncated', () => {
    expect(runLogsUrl(Array.from({ length: 40 }, (_, i) => `i${i}`))!.truncated).toBe(false);
  });
  it('empty list (or only blanks/placeholders) returns null', () => {
    expect(runLogsUrl([])).toBeNull();
    expect(runLogsUrl(['', 'cell-abc', 'human-s1'])).toBeNull();
  });
  it('skips placeholder ids and de-duplicates', () => {
    const r = runLogsUrl(['a', 'a', 'cell-0123', 'human-s1', 'b'])!;
    expect(r).toMatchObject({ used: 2, total: 2, truncated: false });
    expect(decodeURIComponent(r.url)).toContain('("a" OR "b")');
  });
  it('isWorkerRunId rejects placeholders', () => {
    expect(isWorkerRunId('cell-x')).toBe(false);
    expect(isWorkerRunId('human-x')).toBe(false);
    expect(isWorkerRunId('')).toBe(false);
    expect(isWorkerRunId('0a1b2c')).toBe(true);
  });
});
