import type { DatasetMetadata, SourceMedia, TranscriptOrigin } from './api';

const MEDIA_LABEL: Record<SourceMedia, string> = { video: 'Video', audio: 'Audio', transcript: 'transcript' };
const MEDIA_ORDER: SourceMedia[] = ['video', 'audio', 'transcript'];
const ORIGIN_LABEL: Record<TranscriptOrigin, string> = {
  human: 'human', auto_captions: 'auto captions', translated: 'translated', stt_ours: 'our speech-to-text',
};

/** Short phrase for what the ORIGINAL source offers, e.g. "Video + audio + transcript". */
export function originalMedia(media: SourceMedia[] = []): string {
  const present = MEDIA_ORDER.filter(m => media.includes(m));
  if (present.length === 0) return 'unknown';
  if (present.length === 1 && present[0] === 'transcript') return 'Transcript only (no audio)';
  return present.map((m, i) => (i === 0 ? MEDIA_LABEL[m] : MEDIA_LABEL[m].toLowerCase())).join(' + ');
}

/** One-line description: Original / Transcript origin / Labels / MITI version. */
export function sourceLine(d: DatasetMetadata): string {
  const parts = [`Original: ${originalMedia(d.source_media)}`];
  if (d.transcript_origin) parts.push(`Transcript: ${ORIGIN_LABEL[d.transcript_origin]}`);
  if (d.labels_summary) parts.push(`Labels: ${d.labels_summary}`);
  if (d.miti_version === null) parts.push('Not MITI-coded');
  else if (d.miti_version) parts.push(`MITI ${d.miti_version}`);
  if (d.label_scheme) parts.push(`Scheme: ${d.label_scheme}`);
  if (d.language && !d.language.toLowerCase().startsWith('en')) parts.push(`Language: ${d.language}`);
  return parts.join(' · ');
}
