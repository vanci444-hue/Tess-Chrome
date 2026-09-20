import { Pcm16Encoder } from "./pcm";
declare const sampleRate: number;
declare class AudioWorkletProcessor {
  port: MessagePort;
  constructor();
}
declare function registerProcessor(
  name: string,
  processor: typeof AudioWorkletProcessor,
): void;
/** Runs off the UI thread. No audio is persisted; transferred buffers leave this scope. */
class TessPcmProcessor extends AudioWorkletProcessor {
  private encoder = new Pcm16Encoder(sampleRate);
  private active = true;
  constructor() {
    super();
    this.port.onmessage = (event) => {
      if (event.data === "finish") {
        this.active = false;
        const tail = this.encoder.flush();
        if (tail) this.port.postMessage(tail, [tail]);
        this.port.postMessage("flushed");
      }
    };
  }
  process(inputs: Float32Array[][]): boolean {
    if (!this.active) return true;
    const channels = inputs[0];
    if (!channels?.length) return true;
    const mono = new Float32Array(channels[0].length);
    for (const channel of channels)
      for (let i = 0; i < mono.length; i++)
        mono[i] += channel[i] / channels.length;
    for (const chunk of this.encoder.push(mono))
      this.port.postMessage(chunk, [chunk]);
    return true;
  }
}
registerProcessor("tess-pcm-16k", TessPcmProcessor);
