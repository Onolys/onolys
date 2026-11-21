import { pickMimeType } from "./mime";
import { captureUrl, playbackUrl } from "./workletUrls";

/**
 * Browser audio engine (no UI). API for the live page:
 *   const e = createAudioEngine({ onCaptureFrame })   // frame = PCM16 16 kHz mono, 20 ms (ArrayBuffer)
 *   await e.start()            // mic (AEC + NS), worklets, recorder; call from a user gesture
 *   e.playPcm24k(buf)          // AI audio (PCM16 24 kHz mono); plays to speakers AND the recording
 *   e.flush()                  // on `interrupted`: drop queued AI audio
 *   const blob = await e.stopRecording()   // mixed mic+AI; recorder keeps running across reconnects
 *   e.mimeType                 // chosen recorder container ("" = browser default)
 *   e.close()                  // stop mic, tear down context
 */
export interface AudioEngine {
  start(): Promise<void>;
  playPcm24k(pcm: ArrayBuffer | Int16Array): void;
  flush(): void;
  stopRecording(): Promise<Blob>;
  readonly mimeType: string;
  close(): void;
}

export function createAudioEngine(opts: { onCaptureFrame: (frame: ArrayBuffer) => void }): AudioEngine {
  let ctx: AudioContext | undefined;
  let stream: MediaStream | undefined;
  let rec: MediaRecorder | undefined;
  let playNode: AudioWorkletNode | undefined;
  let mimeType = "";
  const chunks: Blob[] = [];

  return {
    get mimeType() {
      return mimeType;
    },
    async start() {
      const Ctor: typeof AudioContext =
        window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctx = new Ctor();
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      await ctx.resume();
      await ctx.audioWorklet.addModule(captureUrl);
      await ctx.audioWorklet.addModule(playbackUrl);

      const dest = ctx.createMediaStreamDestination();
      const mic = ctx.createMediaStreamSource(stream);
      mic.connect(dest);

      const capNode = new AudioWorkletNode(ctx, "capture", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
      capNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => opts.onCaptureFrame(e.data);
      const mute = ctx.createGain();
      mute.gain.value = 0; // keep the capture node pulled without echoing the mic
      mic.connect(capNode);
      capNode.connect(mute).connect(ctx.destination);

      playNode = new AudioWorkletNode(ctx, "playback", { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1] });
      const aiGain = ctx.createGain();
      playNode.connect(aiGain).connect(dest);
      playNode.connect(ctx.destination);

      mimeType = pickMimeType();
      rec = new MediaRecorder(dest.stream, mimeType ? { mimeType } : undefined);
      if (rec.mimeType) mimeType = rec.mimeType;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      rec.start(1000);
    },
    playPcm24k(pcm) {
      if (!playNode) return;
      const copy = pcm instanceof Int16Array ? pcm.slice().buffer : pcm.slice(0);
      playNode.port.postMessage(copy, [copy]);
    },
    flush() {
      playNode?.port.postMessage("flush");
    },
    stopRecording() {
      const r = rec;
      if (!r) return Promise.reject(new Error("recording not started"));
      return new Promise<Blob>((resolve) => {
        const done = () => resolve(new Blob(chunks, { type: mimeType || r.mimeType }));
        if (r.state === "inactive") return done();
        r.onstop = done;
        r.stop();
      });
    },
    close() {
      stream?.getTracks().forEach((t) => t.stop());
      void ctx?.close();
      playNode = undefined;
    },
  };
}
