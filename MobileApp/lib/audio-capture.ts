/**
 * Microphone capture → 16 kHz PCM16 chunks + live RMS level.
 *
 * Use:
 *   const cap = new MicCapture();
 *   await cap.start({
 *     onChunk: (pcm16Chunk) => session.sendAudio(pcm16Chunk),
 *     onLevel: (rms) => setMeter(rms),
 *   });
 */
export interface MicCaptureHandlers {
  onChunk: (pcm16: ArrayBuffer) => void;
  onLevel?: (rms: number) => void;
}

export class MicCapture {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;
  private chunkCount = 0;

  async start(handlers: MicCaptureHandlers): Promise<void> {
    if (this.ctx) return;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") await this.ctx.resume();

    await this.ctx.audioWorklet.addModule("/audio-capture-worklet.js");

    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "capture-worklet", {
      processorOptions: { targetRate: 16000 },
    });
    this.node.port.onmessage = (e) => {
      const data = e.data as
        | { kind: "audio"; buffer: ArrayBuffer }
        | { kind: "level"; level: number };
      if (data.kind === "audio") {
        this.chunkCount++;
        if (this.chunkCount === 1) {
          // eslint-disable-next-line no-console
          console.log(
            "[MicCapture] first chunk delivered",
            data.buffer.byteLength,
            "bytes",
          );
        }
        handlers.onChunk(data.buffer);
      } else if (data.kind === "level") {
        handlers.onLevel?.(data.level);
      }
    };

    // CRITICAL: AudioWorkletNode.process() only runs when the node has a
    // downstream consumer. Route through a muted gain so we don't actually
    // monitor the mic to the speakers.
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    src.connect(this.node);
    this.node.connect(this.sink);
    this.sink.connect(this.ctx.destination);

    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  async stop(): Promise<void> {
    try {
      this.node?.disconnect();
      this.sink?.disconnect();
    } catch {
      // ignore — disconnect of already-disconnected nodes throws on Safari
    }
    this.node = null;
    this.sink = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.ctx) {
      await this.ctx.close();
      this.ctx = null;
    }
    if (this.chunkCount === 0) {
      // eslint-disable-next-line no-console
      console.warn(
        "[MicCapture] stopped without delivering any chunks — mic permission?",
      );
    }
    this.chunkCount = 0;
  }
}
