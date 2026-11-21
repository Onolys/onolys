// Vite bundles each worklet (with its imports) into its own same-origin .js asset (CSP script-src 'self', no blob:).
import captureUrl from "./capture.worklet.ts?worker&url";
import playbackUrl from "./playback.worklet.ts?worker&url";

export { captureUrl, playbackUrl };
