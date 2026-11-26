import { describe, expect, it } from 'vitest';
import { describeError, ERROR_CATALOG, KNOWN_ERROR_CODES } from './errorCatalog';

const REQUIRED = ['invalid_parameters', 'provider_unavailable', 'provider_error', 'rate_limited', 'timeout', 'internal_error', 'provider_skipped',
  'upstream_unavailable', 'deadline_exceeded', 'output_invalid', 'invalid_coded_span', 'session_too_long', 'transcription_failed', 'no_speech', 'speakers_not_separated',
  'enqueue_failed', 'execution_config_changed', 'cancelled', 'gold_unavailable', 'unknown'];

describe('errorCatalog', () => {
  it.each(REQUIRED)('has a complete entry for %s', code => {
    const e = describeError(code);
    expect(e.code).toBe(code);
    expect(e.known).toBe(true);
    expect(e.title.length).toBeGreaterThan(2);
    expect(e.explanation.length).toBeGreaterThan(10);
    expect(e.fix.length).toBeGreaterThan(10);
  });
  it('lists every known code and no entry is empty', () => {
    expect(KNOWN_ERROR_CODES).toEqual(expect.arrayContaining(REQUIRED));
    for (const code of KNOWN_ERROR_CODES) for (const k of ['title', 'explanation', 'fix'] as const) expect(ERROR_CATALOG[code][k].trim()).not.toBe('');
  });
  it('explains invalid_parameters as rejected engine params with the stt_run example', () => {
    const e = describeError('invalid_parameters');
    expect(e.explanation).toMatch(/rejected/i);
    expect(e.explanation).toMatch(/stt_run/);
    expect(e.explanation).toMatch(/PR #77/);
  });
  it('unknown code keeps the code verbatim with a generic hint', () => {
    const e = describeError('weird_new_code');
    expect(e).toMatchObject({ code: 'weird_new_code', known: false, title: 'weird_new_code' });
    expect(e.explanation).toMatch(/not recognised|unrecognised|not recognized/i);
    expect(e.fix.length).toBeGreaterThan(10);
  });
  it.each([undefined, null, '', '   '])('empty code %j gives a generic no-code entry', code => {
    const e = describeError(code);
    expect(e.known).toBe(false);
    expect(e.code).toBe('');
    expect(e.title).toBe('Unknown error');
    expect(e.fix.length).toBeGreaterThan(10);
  });
  it('does not match Object.prototype keys', () => {
    expect(describeError('constructor').known).toBe(false);
    expect(describeError('toString').known).toBe(false);
  });
});
