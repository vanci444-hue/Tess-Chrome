/** Streaming box resampler. Fractional coverage is carried across AudioWorklet quanta. */
export class Pcm16Encoder {
  private weighted = 0;
  private covered = 0;
  private pending: number[] = [];
  private readonly ratio: number;
  private readonly outputRate: number;
  private readonly chunkMs: number;
  constructor(inputRate: number, outputRate = 16000, chunkMs = 100) {
    if (inputRate <= 0 || outputRate <= 0)
      throw new Error("Invalid sample rate");
    this.outputRate = outputRate;
    this.chunkMs = chunkMs;
    this.ratio = inputRate / outputRate;
  }
  push(samples: Float32Array): ArrayBuffer[] {
    const chunks: ArrayBuffer[] = [];
    const size = Math.round((this.outputRate * this.chunkMs) / 1000);
    for (const sample of samples) {
      let remaining = 1;
      while (remaining > 1e-9) {
        const take = Math.min(remaining, this.ratio - this.covered);
        this.weighted += sample * take;
        this.covered += take;
        remaining -= take;
        if (this.covered >= this.ratio - 1e-9) {
          const normalized = Math.max(
            -1,
            Math.min(1, this.weighted / this.ratio),
          );
          this.pending.push(
            Math.round(normalized * (normalized < 0 ? 32768 : 32767)),
          );
          this.covered = 0;
          this.weighted = 0;
          if (this.pending.length === size) {
            chunks.push(this.pack());
          }
        }
      }
    }
    return chunks;
  }
  flush(): ArrayBuffer | null {
    return this.pending.length ? this.pack() : null;
  }
  private pack(): ArrayBuffer {
    const bytes = new ArrayBuffer(this.pending.length * 2),
      view = new DataView(bytes);
    this.pending.forEach((sample, index) =>
      view.setInt16(index * 2, sample, true),
    );
    this.pending = [];
    return bytes;
  }
}
