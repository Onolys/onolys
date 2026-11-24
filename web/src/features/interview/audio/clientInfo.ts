/** Bump when the capture/playback/recording pipeline in `engine.ts` changes, so logs tell builds apart. */
export const AUDIO_ENGINE_VERSION = 1;
export const AUDIO_ENGINE = `worklet-pcm16@${AUDIO_ENGINE_VERSION}`;

/** The optional `client` object of interview-end and session-create (02-logging R13). */
export function clientInfo(engine: { mimeType: string }): { recorder_mime?: string; audio_engine: string } {
  return { ...(engine.mimeType ? { recorder_mime: engine.mimeType } : {}), audio_engine: AUDIO_ENGINE };
}
