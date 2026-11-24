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
});
