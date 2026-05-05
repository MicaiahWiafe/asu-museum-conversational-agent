# AR Gallery — Conversational RAG Agent

A conversational AI gallery guide for the ASU Museum's Carmen Lomas Garza
exhibition. Visitors hold spoken, low-latency conversations grounded in a
curated knowledge base about the artworks, the artist, and the cultural
context of her work.

**Two clients hit one backend:**

- **Mobile (primary, MVP)** — a Next.js PWA that uses **Gemini Live** for
  realtime full-duplex voice (Aoede, warm-female-educator voice). Free tier;
  sub-second latency.
- **Quest MR (secondary, in-museum installation)** — the existing Unity 6
  app uses the Anthropic + ElevenLabs path with HRTF spatial audio at
  artwork anchors.

Both clients call the same `/retrieve` endpoint and use the same Chroma
store. Grounding is identical; only the LLM/STT/TTS surface differs.

## Repo layout

```
.
├── Backend/                          # FastAPI — serves both Mobile (Gemini Live) and Quest (Anthropic) paths
│   ├── main.py                       # Routes: /retrieve, /artworks, /voice/ws (mobile); /query, /transcribe, /session/start (Quest); /health
│   ├── config.py                     # pydantic-settings; relative paths anchor to Backend/
│   ├── models.py                     # Pydantic request/response models — the API contract
│   ├── retrieval.py                  # Shared retrieval (top-5 + forced bio chunk + char budget) — used by /retrieve, /query, and Gemini tool calls
│   ├── voice_session.py              # Gemini Live WebSocket relay (mobile path)
│   ├── rag_pipeline.py               # Anthropic SDK + system prompt (Quest path)
│   ├── vector_store.py               # ChromaStore + VectorStore Protocol (Pinecone swap-point)
│   ├── artwork_registry.py           # Loads KnowledgeBase/artworks.json
│   ├── session_manager.py            # In-memory sessions (no TTL — MVP, Quest only)
│   ├── tts_service.py                # ElevenLabs + sha256 disk cache → /audio/{hash}.mp3 (Quest only)
│   ├── stt_service.py                # OpenAI Whisper API (Quest only)
│   ├── tests/                        # pytest — runs without API keys
│   ├── requirements.txt
│   └── .env.example
│
├── MobileApp/                        # Next.js 15 PWA (TypeScript + Tailwind, static export)
│   ├── app/                          # App Router: layout.tsx, page.tsx, globals.css
│   ├── components/                   # ArtworkPicker, PushToTalkButton, TranscriptStream
│   ├── lib/                          # api.ts, audio-capture.ts, audio-playback.ts, voice-session.ts
│   ├── public/                       # manifest.json + audio-capture-worklet.js
│   ├── package.json                  # next 15, react 19, tailwind 3
│   └── README.md
│
├── Unity/ASUGallery/                 # Unity 6 project (Mixed Reality template, 6000.4.4f1)
│   ├── Assets/_Project/              # Our own content, separated from template assets
│   │   └── ConversationalAgent/
│   │       ├── Scripts/
│   │       │   ├── ConversationalAgent.cs    # The only file that talks to the backend
│   │       │   ├── SessionState.cs           # DontDestroyOnLoad singleton, owns session_id
│   │       │   ├── VoiceCapture.cs           # Microphone → 16-bit PCM WAV (200ms leading trim)
│   │       │   ├── AgentAudioPlayer.cs       # Spatial audio playback (HRTF, spatialBlend = 1)
│   │       │   └── ArtworkContext.cs         # Static Current — set by gaze/proximity triggers
│   │       ├── Editor/                       # Custom inspector + "Test /health" button
│   │       ├── Tests/                        # EditMode tests (NUnit)
│   │       └── *.asmdef                      # Three assemblies: runtime, editor, tests
│   └── Packages/manifest.json        # URP, XR Interaction Toolkit, OpenXR + Meta OpenXR, AR Foundation
│
├── KnowledgeBase/
│   ├── raw/                          # Curated source docs (.md / .txt) — one per artwork + bio
│   ├── chunks/                       # JSONL output of ingest.py — generated, do not hand-edit
│   ├── artworks.json                 # Registry: id, title, year, medium, description
│   └── ingest.py                     # Idempotent: chunks → embeds → upserts into Chroma
│
└── Docs/
    ├── SETUP.md                      # End-to-end setup from a fresh clone
    └── ARCHITECTURE.md               # Request flow + extension points
```

## Tech stack (locked)

**Shared:**
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (local, CPU,
  no API cost). ~80 MB on first download.
- **Vector store**: Chroma `PersistentClient` for dev. `vector_store.py`
  exposes a `VectorStore` Protocol so a `PineconeStore` can be swapped in
  for production with no other file changes.
- **Backend**: FastAPI + Pydantic v2 + pydantic-settings. Python 3.9+.

**Mobile path (primary):**
- **Voice**: Gemini Live API (`gemini-live-2.5-flash-preview`) — full-duplex
  STT + LLM + TTS in one streaming pipeline. Free tier on AI Studio.
- **Voice ID**: Aoede (warm, female, educator-leaning prebuilt voice).
- **RAG**: Gemini calls `retrieve_chunks(query)` as a tool; the FastAPI
  backend executes the call against Chroma and returns the same chunks
  the Quest path's prompt-cached Claude system would have used.
- **Client**: Next.js 15 PWA, TypeScript, Tailwind. Static export so it
  deploys to Vercel/S3/GitHub Pages with no server runtime.
- **Audio**: Web Audio AudioWorklet for 16 kHz PCM16 mic capture; chained
  AudioBufferSource for 24 kHz PCM16 streaming playback.

**Quest path (secondary, in-museum installation):**
- **LLM**: Anthropic `claude-sonnet-4-6` via the official `anthropic` SDK.
  System prompt + retrieved chunks placed in a
  `cache_control: {type: "ephemeral"}` block.
- **STT**: OpenAI Whisper API (`whisper-1`).
- **TTS**: ElevenLabs HTTP API. Outputs cached on disk by sha256 and
  served from a `/audio/{hash}.mp3` static mount.
- **Client**: Unity 6 / 2022 LTS, URP, Meta XR SDK, XR Interaction Toolkit.
  Network calls use plain `UnityWebRequest` in coroutines.

## API contract

Defined verbatim in [Backend/models.py](Backend/models.py:1).

**Shared:**
```
GET  /health                                                  → { status, vector_store, llm }
GET  /artworks                                                → { artworks: [...] }
POST /retrieve { query, artwork_id?, k? }                     → { chunks: [...] }
POST /identify-artwork { image_base64 }                       → { artwork_id, confidence, reason }
```

**Mobile path:**
```
WS   /voice/ws    (browser opens, sends {artwork_id} setup)
       ↑↓ binary frames: 16 kHz PCM16 in / 24 kHz PCM16 out
       ↑↓ text JSON events: ready / tool_call / transcript / turn_complete / error
       ↑   text JSON ctrl: {"type":"end_turn"} on push-to-talk release
```
Wire format owned by [Backend/voice_session.py](Backend/voice_session.py:1)
and [MobileApp/lib/voice-session.ts](MobileApp/lib/voice-session.ts:1).
Move them in lockstep.

**Quest path:**
```
POST /session/start  { language }                             → { session_id }
POST /transcribe     { audio_base64, language }               → { transcript, confidence }
POST /query          { session_id, artwork_id, query_text,
                       language, visited_artworks }           → { response_text, audio_url,
                                                                  source_chunks, session_id }
GET  /audio/{hash}.mp3                                        → audio/mpeg
```
Wire format owned by [Backend/models.py](Backend/models.py:1) and
[Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs](Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs:1).

## RAG behavior

1. Top-5 chunks from Chroma, filtered by `artwork_id` when present.
2. Force-include one general-bio chunk (sourced from `artist_biography.*`)
   if not already in the result set.
3. Truncate to ~1500 tokens (~6000 chars) of retrieved content.
4. Build the system prompt from the template in
   [Backend/rag_pipeline.py](Backend/rag_pipeline.py:10) (artwork title +
   year + medium + visited list + retrieved context).
5. Call `claude-sonnet-4-6` with the system block cached.
6. Response: 2-4 conversational sentences, English (Spanish in Tier 2).

## MVP scope (locked)

**In:** English only, push-to-talk, Quest MR, single artwork at a time,
in-memory sessions, hash-cached TTS, Chroma local persistence.

**Deferred (out of scope for this pass):**
- Spanish (Tier 2)
- Streaming TTS (Tier 2)
- Always-on listening (Tier 2)
- Pinecone production wiring (`VectorStore` interface only)
- Unity scene, prefabs, ProjectSettings, XR rig setup
- Auth header on Unity → Backend calls (production-only)
- Real KB content + populated `artworks.json`
- Session TTL / eviction in `session_manager`

## Conventions

- **Artwork IDs**: snake_case slugs. The same string is used as:
  - the `id` field in `KnowledgeBase/artworks.json`
  - the basename of the source doc (`raw/{id}.md`)
  - the GameObject name of the artwork's anchor in the Unity scene
  - the `artwork_id` the Unity client sends in `/query`
- The artist biography file must be named `artist_biography.md` (or `.txt`)
  — the ingester recognizes it by name and stores it without an `artwork_id`,
  which is what makes the "force one bio chunk" rule work.
- Re-running `python KnowledgeBase/ingest.py` is **always safe**. Chunks for
  each source file are deleted before re-insertion.

## Common commands

```bash
# Backend (from Backend/)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # then fill in keys (GEMINI_API_KEY required for mobile)
uvicorn main:app --reload --port 8000
pytest                              # 9 tests, no keys required

# Knowledge base (from KnowledgeBase/)
python ingest.py                    # idempotent re-ingest of raw/

# Mobile (from MobileApp/)
npm install
cp .env.example .env.local          # set NEXT_PUBLIC_BACKEND_BASE_URL
npm run dev                         # http://localhost:3000

# Smoke tests
curl http://localhost:8000/health
curl http://localhost:8000/artworks | jq '.artworks | length'
curl -X POST http://localhost:8000/retrieve \
  -H 'content-type: application/json' \
  -d '{"query":"why does Carmen paint family scenes","artwork_id":"tamalada"}'
```

See [Docs/SETUP.md](Docs/SETUP.md) for the full step-by-step (including the
Unity side) and [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md) for the request
flow diagram and extension points.

## When making changes

- **Mobile voice contract change** → edit
  [Backend/voice_session.py](Backend/voice_session.py:1) AND
  [MobileApp/lib/voice-session.ts](MobileApp/lib/voice-session.ts:1).
- **Quest API contract change** → edit
  [Backend/models.py](Backend/models.py:1) AND the DTOs in
  [Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs](Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs:1).
- **Retrieval/grounding change** (top-k, char budget, bio-chunk rule) →
  only [Backend/retrieval.py](Backend/retrieval.py:1). Both clients use
  it through `/retrieve` and the Gemini tool call.
- **Prompt or retrieval change** → only
  [Backend/rag_pipeline.py](Backend/rag_pipeline.py:1).
- **Vector store swap (Chroma → Pinecone)** → only
  [Backend/vector_store.py](Backend/vector_store.py:1) and the
  `get_vector_store()` factory in [Backend/main.py](Backend/main.py:42).
- **New artwork** → see "Adding a new artwork" in
  [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md).
- **New Unity-side network call** →
  [Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs](Unity/ASUGallery/Assets/_Project/ConversationalAgent/Scripts/ConversationalAgent.cs:1)
  is the only file that should ever import `UnityWebRequest` for backend
  traffic. Keep it that way.
