# Architecture

Single-paragraph version: the Unity client captures a push-to-talk utterance,
ships it to a Python FastAPI backend, which transcribes (Whisper), retrieves
relevant chunks from a Chroma vector store keyed by artwork, asks Claude for a
grounded 2-4 sentence answer, synthesizes it with ElevenLabs, and returns text
+ a cached audio URL the client plays back at the artwork's anchor with HRTF.

## Request flow

```
+----------------+        push-to-talk WAV (b64)        +-------------------+
| Unity client   | ----------------------------------> | POST /transcribe   |
| (Quest MR)     |                                     |  Whisper-1         |
|                | <---- transcript -----              +-------------------+
|                |
|                |        artwork_id + transcript      +-------------------+
|                | ----------------------------------> | POST /query        |
|                |                                     |   Chroma top-5     |
|                |                                     |   + bio chunk      |
|                |                                     |   -> Claude        |
|                |                                     |   -> ElevenLabs    |
|                | <-- text + /audio/{hash}.mp3 -----  +-------------------+
|                |
|                |        GET /audio/{hash}.mp3        +-------------------+
|                | ----------------------------------> | StaticFiles mount  |
|  HRTF playback | <---- mp3 bytes -----               +-------------------+
+----------------+
```

## Client/backend boundary

The Unity package (`Assets/ConversationalAgent/`) only talks to the backend
through one file: `ConversationalAgent.cs`. All other scripts are domain types
or Unity-engine wrappers. If the API contract changes, only this file and
`Backend/models.py` need to move in lockstep.

## Adding a new artwork

1. Add an entry to `KnowledgeBase/artworks.json` with a snake_case `id`.
2. Drop a Markdown source document at `KnowledgeBase/raw/{id}.md`.
3. Run `python KnowledgeBase/ingest.py`.
4. In the Unity scene, name the artwork's anchor GameObject `{id}` so gaze /
   proximity triggers populate `ArtworkContext.Current` with that id.

No backend restart required — the registry is loaded lazily and chunks live in
the persistent Chroma store. (Restart only needed if you change `artworks.json`
*and* are mid-session.)

## Swapping Chroma for Pinecone

`Backend/vector_store.py` exposes a `VectorStore` Protocol. Add a
`PineconeStore` class implementing the same `add_chunks` / `query` /
`delete_by_source` / `count` methods, then change `get_vector_store()` in
`main.py` to construct it instead of `ChromaStore`. No other file changes.

## What's NOT here yet

- Spanish (Tier 2; backend already accepts `language: "es"`, voice IDs unused)
- Streaming TTS (Tier 2)
- Always-on listening (Tier 2)
- Auth header on Unity → Backend calls (production-only)
- Session TTL eviction (sessions accumulate in memory until restart)
- Production Pinecone wiring (interface only)
