/**
 * WebSocket client to the FastAPI /voice/ws relay.
 *
 * Wire format matches Backend/voice_session.py:
 *   - First message: text JSON {artwork_id?: string}
 *   - Mic audio: binary frames (16-bit PCM, 16 kHz, mono)
 *   - Push-to-talk release: text JSON {type: "end_turn"}
 *
 * Server emits:
 *   - text JSON events (ready / tool_call / transcript / turn_complete / error)
 *   - binary frames: 16-bit PCM, 24 kHz, mono — Gemini's spoken response
 */

export type ConversationTurn = {
  role: "user" | "model";
  text: string;
};

export type ServerEvent =
  | { type: "ready"; artwork_id: string | null }
  | { type: "tool_call"; name: string; query: string; chunks: string[] }
  | { type: "transcript"; text: string }
  | { type: "input_transcript"; text: string }
  | { type: "turn_complete" }
  | { type: "heartbeat" }
  | { type: "error"; message: string };

export interface VoiceSessionHandlers {
  onAudio: (pcm16: ArrayBuffer) => void;
  onEvent: (event: ServerEvent) => void;
  onClose?: () => void;
}

export class VoiceSession {
  private ws: WebSocket | null = null;
  private opened = false;

  constructor(
    private readonly baseUrl: string,
    private readonly handlers: VoiceSessionHandlers,
  ) {}

  async connect(
    artworkId: string | null,
    history: ConversationTurn[] = [],
  ): Promise<void> {
    const wsUrl =
      this.baseUrl.replace(/^http/, "ws").replace(/\/$/, "") + "/voice/ws";
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        ws.removeEventListener("error", onErr);
        resolve();
      };
      const onErr = (e: Event) => {
        ws.removeEventListener("open", onOpen);
        reject(new Error("websocket error: " + (e as ErrorEvent).message));
      };
      ws.addEventListener("open", onOpen, { once: true });
      ws.addEventListener("error", onErr, { once: true });
    });

    this.opened = true;
    // Backend prefills the new Live session with this history before
    // accepting the visitor's new input — the conversation feels
    // continuous even though we open a fresh session per turn.
    ws.send(JSON.stringify({ artwork_id: artworkId, history }));

    ws.addEventListener("message", (e) => {
      if (e.data instanceof ArrayBuffer) {
        this.handlers.onAudio(e.data);
      } else if (typeof e.data === "string") {
        try {
          const evt = JSON.parse(e.data) as ServerEvent;
          this.handlers.onEvent(evt);
        } catch {
          // Ignore malformed text frame.
        }
      }
    });

    ws.addEventListener("close", () => {
      this.opened = false;
      this.handlers.onClose?.();
    });
  }

  sendAudio(pcm16: ArrayBuffer): void {
    if (this.opened && this.ws) this.ws.send(pcm16);
  }

  startTurn(): void {
    if (this.opened && this.ws)
      this.ws.send(JSON.stringify({ type: "start_turn" }));
  }

  endTurn(): void {
    if (this.opened && this.ws)
      this.ws.send(JSON.stringify({ type: "end_turn" }));
  }

  /**
   * Submit a typed question. Lands in the same Gemini Live session as
   * voice turns, so conversation memory carries across modalities.
   * The model will respond with spoken audio just like for a voice turn.
   */
  sendText(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (this.opened && this.ws)
      this.ws.send(JSON.stringify({ type: "text_turn", text: trimmed }));
  }

  close(): void {
    this.opened = false;
    this.ws?.close();
    this.ws = null;
  }
}
