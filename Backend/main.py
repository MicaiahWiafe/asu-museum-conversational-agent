from contextlib import asynccontextmanager
from functools import lru_cache

from anthropic import Anthropic
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from artwork_registry import ArtworkRegistry
from config import Settings, get_settings
from models import (
    ArtworkInfo,
    ArtworksResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunkOut,
    SessionStartRequest,
    SessionStartResponse,
    TranscribeRequest,
    TranscribeResponse,
)
from rag_pipeline import RagPipeline
from retrieval import retrieve as retrieve_chunks
from session_manager import SessionManager
from stt_service import STTService
from tts_service import TTSService
from vector_store import ChromaStore, VectorStore
from voice_session import run_voice_session


# --- Dependency factories (lazy, cached). Tests override these. ---


@lru_cache(maxsize=1)
def get_session_manager() -> SessionManager:
    return SessionManager()


@lru_cache(maxsize=1)
def get_artwork_registry() -> ArtworkRegistry:
    s = get_settings()
    return ArtworkRegistry(s.artworks_json_path)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    s = get_settings()
    return ChromaStore(
        persist_dir=s.chroma_persist_path,
        collection=s.chroma_collection,
        embedding_model=s.embedding_model,
    )


@lru_cache(maxsize=1)
def get_anthropic_client() -> Anthropic:
    s = get_settings()
    return Anthropic(api_key=s.anthropic_api_key or None)


def get_rag_pipeline(
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    registry: ArtworkRegistry = Depends(get_artwork_registry),
    client: Anthropic = Depends(get_anthropic_client),
) -> RagPipeline:
    return RagPipeline(
        vector_store=store,
        registry=registry,
        anthropic_client=client,
        model=settings.anthropic_model,
    )


@lru_cache(maxsize=1)
def get_tts_service() -> TTSService:
    s = get_settings()
    return TTSService(
        api_key=s.elevenlabs_api_key,
        voice_id_en=s.elevenlabs_voice_id_en,
        voice_id_es=s.elevenlabs_voice_id_es,
        model_id=s.elevenlabs_model_id,
        cache_dir=s.tts_cache_path,
    )


@lru_cache(maxsize=1)
def get_stt_service() -> STTService:
    s = get_settings()
    return STTService(api_key=s.openai_api_key, model=s.whisper_model)


# --- App setup ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.tts_cache_path.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(s.tts_cache_path)), name="audio")
    yield


app = FastAPI(title="AR Gallery Conversational Agent", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ---


@app.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    vs_status = "ok"
    try:
        get_vector_store().count()
    except Exception:
        vs_status = "unavailable"

    llm_status = "ok" if settings.anthropic_api_key else "unavailable"
    overall = "ok" if vs_status == "ok" and llm_status == "ok" else "degraded"
    return HealthResponse(status=overall, vector_store=vs_status, llm=llm_status)


@app.post("/session/start", response_model=SessionStartResponse)
def session_start(
    body: SessionStartRequest,
    sessions: SessionManager = Depends(get_session_manager),
) -> SessionStartResponse:
    state = sessions.create_session(language=body.language)
    return SessionStartResponse(session_id=state.session_id)


@app.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    sessions: SessionManager = Depends(get_session_manager),
    registry: ArtworkRegistry = Depends(get_artwork_registry),
    rag: RagPipeline = Depends(get_rag_pipeline),
    tts: TTSService = Depends(get_tts_service),
) -> QueryResponse:
    if sessions.get(body.session_id) is None:
        raise HTTPException(status_code=404, detail="unknown session_id")

    if body.artwork_id and not registry.exists(body.artwork_id):
        raise HTTPException(
            status_code=400, detail=f"unknown artwork_id: {body.artwork_id}"
        )

    result = rag.answer(
        query=body.query_text,
        artwork_id=body.artwork_id,
        language=body.language,
        visited=body.visited_artworks,
    )
    sessions.record_turn(body.session_id, body.artwork_id)

    audio_url = None
    try:
        audio_url = tts.synthesize(result.response_text, language=body.language)
    except Exception:
        # Audio is best-effort. Client falls back to text-only display.
        audio_url = None

    return QueryResponse(
        response_text=result.response_text,
        audio_url=audio_url,
        source_chunks=result.source_chunks,
        session_id=body.session_id,
    )


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe(
    body: TranscribeRequest,
    stt: STTService = Depends(get_stt_service),
) -> TranscribeResponse:
    try:
        text, conf = stt.transcribe(body.audio_base64, language=body.language)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"transcription failed: {exc}")
    return TranscribeResponse(transcript=text, confidence=conf)


# --- Mobile / Gemini Live path ---


@app.get("/artworks", response_model=ArtworksResponse)
def list_artworks(
    registry: ArtworkRegistry = Depends(get_artwork_registry),
) -> ArtworksResponse:
    return ArtworksResponse(
        artworks=[
            ArtworkInfo(
                id=a.id,
                title=a.title,
                artist=a.artist,
                year=a.year,
                medium=a.medium,
                description=a.description,
            )
            for a in registry.all()
        ]
    )


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(
    body: RetrieveRequest,
    store: VectorStore = Depends(get_vector_store),
    registry: ArtworkRegistry = Depends(get_artwork_registry),
) -> RetrieveResponse:
    """Curated chunks for a free-form query, optionally scoped to one artwork.
    Same grounding rules as /query and the Gemini Live tool call.
    """
    if body.artwork_id and not registry.exists(body.artwork_id):
        raise HTTPException(
            status_code=400, detail=f"unknown artwork_id: {body.artwork_id}"
        )
    result = retrieve_chunks(
        store=store,
        registry=registry,
        query=body.query,
        artwork_id=body.artwork_id,
        k=body.k,
    )
    return RetrieveResponse(
        chunks=[
            RetrievedChunkOut(
                chunk_id=c.chunk_id,
                source=c.source,
                artwork_id=c.artwork_id,
                text=c.text,
                score=round(c.score, 4),
            )
            for c in result.chunks
        ]
    )


@app.websocket("/voice/ws")
async def voice_ws(
    ws: WebSocket,
):
    """Realtime voice tour-guide over Gemini Live.

    Browser sends:
      - text JSON {"artwork_id": "tamalada"}  (one-shot setup; required first)
      - text JSON {"type": "end_turn"}        (push-to-talk released)
      - binary frames: 16-bit PCM, 16 kHz, mono mic audio chunks

    Server sends:
      - text JSON {"type": "ready", ...}
      - text JSON {"type": "tool_call", ...}     (debug/observability)
      - text JSON {"type": "transcript", ...}    (output captions)
      - text JSON {"type": "turn_complete"}
      - text JSON {"type": "error", ...}
      - binary frames: 16-bit PCM, 24 kHz, mono response audio
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        await ws.close(code=1011, reason="GEMINI_API_KEY not set")
        return
    await ws.accept()
    try:
        await run_voice_session(
            ws=ws,
            api_key=settings.gemini_api_key,
            model=settings.gemini_live_model,
            voice_name=settings.gemini_voice_name,
            store=get_vector_store(),
            registry=get_artwork_registry(),
        )
    finally:
        try:
            await ws.close()
        except Exception:
            pass
