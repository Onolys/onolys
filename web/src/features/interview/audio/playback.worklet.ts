/// <reference lib="webworker" />
// AudioWorklet: 24 kHz PCM16 chunks -> ring buffer -> context rate. Message "flush" clears the ring.
import { PlaybackRing } from "./dsp";

declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, ctor: new () => AudioWorkletProcessor): void;

class Playback extends AudioWorkletProcessor {
  private readonly ring = new PlaybackRing(sampleRate);
  constructor() {
    super();
    this.port.onmessage = (e: MessageEvent<ArrayBuffer | "flush">) => {
      if (e.data === "flush") this.ring.flush();
      else this.ring.writePcm16(new Int16Array(e.data));
    };
  }
  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const out = outputs[0]?.[0];
    if (out) this.ring.read(out);
    return true;
  }
}
registerProcessor("playback", Playback);
