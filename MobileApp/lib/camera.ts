/**
 * Rear-camera capture for artwork identification.
 *
 * Use:
 *   const cam = new CameraCapture();
 *   await cam.start(videoEl);   // streams live preview into <video>
 *   const jpegB64 = cam.snapshot(videoEl, 1280);
 *   await cam.stop();
 *
 * The phone's environment-facing (back) camera is requested by default.
 * Falls back silently to the user-facing camera if no back camera exists
 * (e.g. desktop with only a webcam).
 */
export class CameraCapture {
  private stream: MediaStream | null = null;

  async start(videoEl: HTMLVideoElement): Promise<void> {
    if (this.stream) return;

    // Prefer the back camera. `ideal` rather than `exact` so desktop
    // browsers (no back camera) still get something rather than failing.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 1280 },
      },
    });
    this.stream = stream;
    videoEl.srcObject = stream;
    videoEl.muted = true;
    // playsInline keeps iOS Safari from going fullscreen.
    videoEl.setAttribute("playsinline", "true");
    await videoEl.play().catch(() => {
      /* iOS sometimes throws on autoplay; the video element will start
         playing once visible. */
    });
  }

  /**
   * Capture the current video frame as a base64-encoded JPEG. The
   * returned string has NO data: URL prefix — backend strips that anyway.
   * `maxLongSide` resizes large frames down to keep upload + Gemini token
   * cost low; quality 0.85 preserves enough detail for visual matching.
   */
  snapshot(videoEl: HTMLVideoElement, maxLongSide = 1280): string {
    const vw = videoEl.videoWidth;
    const vh = videoEl.videoHeight;
    if (vw === 0 || vh === 0) {
      throw new Error("camera not ready yet");
    }
    const longSide = Math.max(vw, vh);
    const scale = longSide > maxLongSide ? maxLongSide / longSide : 1;
    const w = Math.round(vw * scale);
    const h = Math.round(vh * scale);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2D context unavailable");
    ctx.drawImage(videoEl, 0, 0, w, h);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
    // Strip the "data:image/jpeg;base64," prefix — server tolerates it,
    // but stripping shaves ~30 bytes off the payload and keeps logs clean.
    const comma = dataUrl.indexOf(",");
    return comma === -1 ? dataUrl : dataUrl.slice(comma + 1);
  }

  async stop(): Promise<void> {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
