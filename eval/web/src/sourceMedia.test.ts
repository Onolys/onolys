import { describe, expect, it } from 'vitest';
import { originalMedia, sourceLine } from './sourceMedia';

describe('source media line', () => {
  it('describes video + audio + transcript with origin, labels and version', () => {
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['transcript', 'audio', 'video'], transcript_origin: 'human', labels_summary: 'MITI counts', miti_version: '4.2.1' }))
      .toBe('Original: Video + audio + transcript · Transcript: human · Labels: MITI counts · MITI 4.2.1');
  });
  it('says transcript only (no audio) and omits missing optional parts', () => {
    expect(originalMedia(['transcript'])).toBe('Transcript only (no audio)');
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['transcript'] })).toBe('Original: Transcript only (no audio)');
  });
  it('shows label scheme, and "Not MITI-coded" when miti_version is null', () => {
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['video'], miti_version: '4.2', label_scheme: 'MITI 4.2' }))
      .toBe('Original: Video · MITI 4.2 · Scheme: MITI 4.2');
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['transcript'], miti_version: null, label_scheme: 'MISC 2.5 mapped to MITI' }))
      .toBe('Original: Transcript only (no audio) · Not MITI-coded · Scheme: MISC 2.5 mapped to MITI');
  });

  it('shows the language only when it is not English', () => {
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['transcript'], language: 'fr' }))
      .toBe('Original: Transcript only (no audio) · Language: fr');
    expect(sourceLine({ dataset_id: 'a', title: 'A', source_media: ['transcript'], language: 'en' }))
      .toBe('Original: Transcript only (no audio)');
  });
});
