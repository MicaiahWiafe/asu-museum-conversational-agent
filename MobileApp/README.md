# ASU Gallery — Mobile PWA

The mobile companion to the AR Gallery RAG agent. A single-page Next.js
app that turns a phone into a low-latency, natural-voice tour guide for
the Carmen Lomas Garza exhibition.

It does not run any LLM or TTS itself. The browser captures mic audio
(16 kHz PCM16), opens a WebSocket to the backend (`/voice/ws`), and
plays back the audio Gemini Live streams down (24 kHz PCM16). All
retrieval is grounded in the same Chroma store as the Quest path.

## Architecture

```
Phone (this app)
   ├── PointerEvent push-to-talk → MicCapture (AudioWorklet, 16 kHz PCM16)
   │                                  │
   │                                  ▼
   │                         WebSocket (/voice/ws)
   │                                  │
   ▼                                  ▼
StreamingPlayer ◀── 24 kHz PCM16 ── Backend (FastAPI)
                                       │
                                       ├── relays audio to Gemini Live
                                       └── handles `retrieve_chunks` tool
                                             calls against Chroma
```

## Develop

```bash
cd MobileApp
npm install
cp .env.example .env.local           # point at your backend
npm run dev                           # http://localhost:3000
```

Test on a real phone (mic / mobile Safari / iOS Home-screen install
quirks rarely show in desktop Chrome):

```bash
# 1. Find your Mac's LAN IP (e.g. 10.0.0.42).
ipconfig getifaddr en0

# 2. In Backend/.env set CORS_ORIGINS=http://10.0.0.42:3000
# 3. In MobileApp/.env.local set NEXT_PUBLIC_BACKEND_BASE_URL=http://10.0.0.42:8000
# 4. Start backend bound to all interfaces (already default HOST=0.0.0.0).
# 5. On the phone, open http://10.0.0.42:3000
```

iOS Safari requires HTTPS for microphone access on non-localhost origins.
For phone testing over LAN, use `mkcert` + a tunneled URL (Tailscale,
ngrok) or run dev over `https://` with a self-signed cert.

## Build (static export → Vercel / S3 / GitHub Pages)

```bash
npm run build
# Outputs ./out — a fully static site. Deploy anywhere.
```

`next.config.ts` sets `output: "export"` so there's no Next.js server
runtime; the backend handles all dynamic work.

## Files

- `app/page.tsx` — the entire UI: artwork picker, push-to-talk, transcript.
- `lib/voice-session.ts` — the only file that touches the WebSocket.
- `lib/audio-capture.ts` + `public/audio-capture-worklet.js` — mic → PCM16.
- `lib/audio-playback.ts` — server PCM16 stream → speakers.

If the API contract on `/voice/ws` changes, `voice-session.ts` and
`Backend/voice_session.py` move in lockstep — those are the only two
files that encode the wire format.
