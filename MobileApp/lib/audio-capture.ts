/**
 * Microphone capture → 16 kHz PCM16 chunks.
 *
 * Use:
 *   const cap = new MicCapture();
 *   await cap.start((pcm16Chunk) => session.sendAudio(pcm16Chunk));
 *   ...
 *   await cap.stop();
 */
export class MicCapture {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;
  private chunkCount = 0;

  async start(onChunk: (pcm16: ArrayBuffer) => void): Promise<void> {
    if (this.ctx) return;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // Some Safari builds lock at 48 kHz regardless of constraint; downsample
    // happens in the worklet anyway.
    this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") await this.ctx.resume();

    await this.ctx.audioWorklet.addModule("/audio-capture-worklet.js");

    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "capture-worklet", {
      processorOptions: { targetRate: 16000 },
    });
    this.node.port.onmessage = (e) => {
      this.chunkCount++;
      if (this.chunkCount === 1) {
        // eslint-disable-next-line no-console
        console.log(
          "[MicCapture] first chunk delivered",
          (e.data as ArrayBuffer).byteLength,
          "bytes",
        );
      }
      onChunk(e.data as ArrayBuffer);
    };

    // CRITICAL: AudioWorkletNode.process() only runs when the node has a
    // downstream consumer. Without this, Safari (and sometimes Chrome under
    // load) silently never calls the processor. Route through a muted gain
    // so we don't actually monitor the mic to the speakers.
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    src.connect(this.node);
    this.node.connect(this.sink);
    this.sink.connect(this.ctx.destination);

    // Belt-and-braces: a fresh resume after the graph is wired (some
    // mobile browsers re-suspend on getUserMedia transitions).
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
