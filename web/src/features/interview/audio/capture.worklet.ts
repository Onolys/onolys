/// <reference lib="webworker" />
// AudioWorklet: mic (context rate) -> 16 kHz mono PCM16 frames, posted as ArrayBuffer.
import { CaptureFramer } from "./dsp";

declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, ctor: new () => AudioWorkletProcessor): void;

class Capture extends AudioWorkletProcessor {
  private readonly framer = new CaptureFramer(sampleRate, (frame) => this.port.postMessage(frame.buffer, [frame.buffer]));
  process(inputs: Float32Array[][]): boolean {
    const ch = inputs[0]?.[0];
    if (ch) this.framer.push(ch);
    return true;
  }
}
registerProcessor("capture", Capture);
