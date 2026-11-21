/** Pure DSP for the interview audio engine (no AudioContext; unit-testable). Used by the worklets and tests. */

export const CAPTURE_RATE = 16000;
export const PLAYBACK_RATE = 24000;
/** 20 ms at 16 kHz. */
export const CAPTURE_FRAME_SAMPLES = 320;

/** Float [-1, 1] -> PCM16 with clamping (asymmetric scale so +1 -> 32767, -1 -> -32768). */
export function floatToPcm16(v: number): number {
  const c = Math.max(-1, Math.min(1, v));
  return Math.round(c < 0 ? c * 0x8000 : c * 0x7fff);
}

export function pcm16ToFloat(v: number): number {
  return v / 0x8000;
}

/**
 * Streaming box-filter downsampler: input at `inputRate` -> mono PCM16 at CAPTURE_RATE,
 * emitted in fixed-size frames. Feed arbitrary-size blocks with `push`.
 */
export class CaptureFramer {
  private readonly ratio: number;
  private buf: Float32Array = new Float32Array(0);
  private pos = 0; // fractional read position into buf
  private out: Int16Array;
  private n = 0;

  constructor(
    inputRate: number,
    private readonly onFrame: (frame: Int16Array) => void,
    private readonly frameSamples = CAPTURE_FRAME_SAMPLES,
  ) {
    this.ratio = inputRate / CAPTURE_RATE;
    this.out = new Int16Array(frameSamples);
  }

  push(block: Float32Array): void {
    const merged = new Float32Array(this.buf.length + block.length);
    merged.set(this.buf);
    merged.set(block, this.buf.length);
    this.buf = merged;
    while (this.pos + this.ratio <= this.buf.length) {
      const a = Math.floor(this.pos);
      const b = Math.max(Math.floor(this.pos + this.ratio), a + 1);
      let sum = 0;
      for (let j = a; j < b; j++) sum += this.buf[j];
      this.out[this.n++] = floatToPcm16(sum / (b - a));
      this.pos += this.ratio;
      if (this.n === this.frameSamples) {
        this.onFrame(this.out.slice());
        this.n = 0;
      }
    }
    const drop = Math.floor(this.pos);
    if (drop > 0) {
      this.buf = this.buf.slice(drop);
      this.pos -= drop;
    }
  }
}

/**
 * Ring buffer of 24 kHz float samples read out at the context rate with linear interpolation.
 * Overflow drops the oldest audio. `flush()` empties it (barge-in / `interrupted`).
 */
export class PlaybackRing {
  private readonly ring: Float32Array;
  private readIdx = 0;
  private count = 0;
  private frac = 0;
  private playing = false;
  /** Number of times the reader ran dry after having produced audio. */
  underruns = 0;
  private readonly step: number;

  constructor(outputRate: number, capacitySamples = PLAYBACK_RATE * 30) {
    this.ring = new Float32Array(capacitySamples);
    this.step = PLAYBACK_RATE / outputRate;
  }

  get buffered(): number {
    return this.count;
  }

  write(samples: Float32Array): void {
    const cap = this.ring.length;
    const src = samples.length > cap ? samples.subarray(samples.length - cap) : samples;
    const overflow = this.count + src.length - cap;
    if (overflow > 0) {
      this.readIdx = (this.readIdx + overflow) % cap;
      this.count -= overflow;
    }
    let w = (this.readIdx + this.count) % cap;
    for (let i = 0; i < src.length; i++) {
      this.ring[w] = src[i];
      w = (w + 1) % cap;
    }
    this.count += src.length;
  }

  writePcm16(pcm: Int16Array): void {
    const f = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) f[i] = pcm16ToFloat(pcm[i]);
    this.write(f);
  }

  flush(): void {
    this.readIdx = 0;
    this.count = 0;
    this.frac = 0;
    this.playing = false;
  }

  /** Fill `out` (context rate); silence when starved. Returns how many samples held real audio. */
  read(out: Float32Array): number {
    const cap = this.ring.length;
    let produced = 0;
    for (let i = 0; i < out.length; i++) {
      if (this.count < 2) {
        out[i] = 0;
        continue;
      }
      const s0 = this.ring[this.readIdx];
      const s1 = this.ring[(this.readIdx + 1) % cap];
      out[i] = s0 + (s1 - s0) * this.frac;
      produced++;
      this.frac += this.step;
      const adv = Math.floor(this.frac);
      this.frac -= adv;
      const take = Math.min(adv, this.count);
      this.readIdx = (this.readIdx + take) % cap;
      this.count -= take;
    }
    if (produced < out.length) {
      if (this.playing) this.underruns++; // ran dry mid-stream
      this.playing = false;
    } else if (produced > 0) {
      this.playing = true;
    }
    return produced;
  }
}
