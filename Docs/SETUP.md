# Setup

End-to-end setup from a fresh clone. Targets macOS / Linux. Windows works with
`venv\Scripts\activate` instead of `source venv/bin/activate`.

## 1. Backend

```bash
cd Backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in the keys you have. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
and at least one `ELEVENLABS_VOICE_ID_*` are required for end-to-end use; the
backend boots and `/health` responds without them, but `/query` will fail.

## 2. Knowledge base

Drop curated source documents into `KnowledgeBase/raw/` (one per artwork,
plus `artist_biography.md`). Populate `KnowledgeBase/artworks.json` with one
entry per artwork — see `KnowledgeBase/README.md` for the schema.

Then re-ingest:

```bash
cd KnowledgeBase
python ingest.py
```

The first run downloads `sentence-transformers/all-MiniLM-L6-v2` (~80 MB).

## 3. Boot the API

```bash
cd Backend
uvicorn main:app --reload --port 8000
```

Smoke test:

```bash
curl http://localhost:8000/health
# {"status":"ok"|"degraded","vector_store":"ok","llm":"ok"|"unavailable"}

# End-to-end /query (requires keys + at least one ingested artwork)
SESSION=$(curl -s -X POST localhost:8000/session/start \
  -H 'content-type: application/json' \
  -d '{"language":"en"}' | python -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')

curl -X POST localhost:8000/query \
  -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"artwork_id\":\"tamalada\",\"query_text\":\"Tell me about this scene.\",\"language\":\"en\",\"visited_artworks\":[]}"
```

## 4. Tests

```bash
cd Backend
pytest
```

`test_health.py` and `test_models.py` pass without any real API keys.

## 5. Unity

1. Open the project in Unity 6 / 2022 LTS with URP + XR Interaction Toolkit + Meta XR SDK.
2. Confirm `Assets/ConversationalAgent/` compiles cleanly.
3. Add `SessionState`, `VoiceCapture`, `AgentAudioPlayer`, and
   `ConversationalAgent` to a single GameObject (or split them — the agent
   references the others via SerializeFields).
4. Set `backendBaseUrl` on `ConversationalAgent` and `SessionState` to your
   dev machine's IP (the Quest can't reach `localhost`).
5. Wire push-to-talk: bind your XR controller's primary button to
   `ConversationalAgent.OnPushToTalkPressed` (down) and
   `OnPushToTalkReleased` (up).
6. Test through Quest Link before deploying to-device.
