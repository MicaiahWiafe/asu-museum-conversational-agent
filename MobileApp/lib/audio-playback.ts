/**
 * Streaming PCM16 @ 24 kHz playback.
 *
 * Each enqueue() schedules a small AudioBuffer to play sequentially. Tiny
 * gaps would click — we maintain a running playhead and chain buffers so
 * they butt up against each other without overlap.
 */
export class StreamingPlayer {
  private ctx: AudioContext | null = null;
  private playhead = 0;
  private readonly sampleRate: number;
  private active = false;

  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate;
  }

  async start(): Promise<void> {
    if (this.ctx) return;
    this.ctx = new AudioContext({ sampleRate: this.sampleRate });
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.playhead = this.ctx.currentTime;
    this.active = true;
  }

  enqueue(pcm16: ArrayBuffer): void {
    if (!this.ctx || !this.active) return;
    const ints = new Int16Array(pcm16);
    if (ints.length === 0) return;

    const buf = this.ctx.createBuffer(1, ints.length, this.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < ints.length; i++) {
      ch[i] = ints[i] / 0x8000;
    }

    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);

    const now = this.ctx.currentTime;
    if (this.playhead < now) this.playhead = now;
    src.start(this.playhead);
    this.playhead += buf.duration;
  }

  /**
   * Drop everything queued. The visitor probably interrupted Gemini —
   * stale audio shouldn't keep playing over their next utterance.
   */
  flush(): void {
    if (!this.ctx) return;
    this.playhead = this.ctx.currentTime;
  }

  async stop(): Promise<void> {
    this.active = false;
    if (this.ctx) {
      await this.ctx.close();
      this.ctx = null;
    }
  }
}
