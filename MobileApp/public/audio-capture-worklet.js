// Captures Float32 mic frames, downsamples to 16 kHz, converts to PCM16,
// and posts ArrayBuffer chunks to the main thread. Frames arrive at the
// AudioContext's native rate (typically 48 kHz on Safari/Chrome mobile).
//
// Decimation is plain integer-step subsampling — fine for speech, no
// anti-alias filter needed because a 48 kHz → 16 kHz drop on phone mic
// audio rarely surfaces audible aliasing.

class CaptureWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const targetRate = (options && options.processorOptions && options.processorOptions.targetRate) || 16000;
    this.step = sampleRate / targetRate;
    this.acc = 0;
    this.pending = [];
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      this.acc += 1;
      if (this.acc >= this.step) {
        this.acc -= this.step;
        // Clamp + Float32 → Int16
        const s = Math.max(-1, Math.min(1, channel[i]));
        this.pending.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      }
    }

    // Flush every ~80 ms-worth of samples (1280 samples @ 16 kHz).
    if (this.pending.length >= 1280) {
      const buf = new Int16Array(this.pending);
      this.pending = [];
      this.port.postMessage(buf.buffer, [buf.buffer]);
    }
    return true;
  }
}

registerProcessor("capture-worklet", CaptureWorklet);
