from typing import Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["en", "es"]


class QueryRequest(BaseModel):
    session_id: str
    artwork_id: Optional[str] = None
    query_text: str
    language: Language = "en"
    visited_artworks: list[str] = Field(default_factory=list)


class SourceChunk(BaseModel):
    chunk_id: str
    source: str
    score: float


class QueryResponse(BaseModel):
    response_text: str
    audio_url: Optional[str] = None
    source_chunks: list[SourceChunk] = Field(default_factory=list)
    session_id: str


class TranscribeRequest(BaseModel):
    audio_base64: str
    language: Language = "en"


class TranscribeResponse(BaseModel):
    transcript: str
    confidence: float = Field(ge=0.0, le=1.0)


class SessionStartRequest(BaseModel):
    language: Language = "en"


class SessionStartResponse(BaseModel):
    session_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    vector_store: Literal["ok", "unavailable"] = "ok"
    llm: Literal["ok", "unavailable"] = "ok"


# --- Mobile / Gemini Live path ---

class RetrieveRequest(BaseModel):
    query: str
    artwork_id: Optional[str] = None
    k: int = Field(default=5, ge=1, le=10)


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    source: str
    artwork_id: Optional[str] = None
    text: str
    score: float


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunkOut] = Field(default_factory=list)


class ArtworkInfo(BaseModel):
    id: str
    title: str
    artist: str
    year: Optional[str] = None
    medium: Optional[str] = None
    description: Optional[str] = None


class ArtworksResponse(BaseModel):
    artworks: list[ArtworkInfo] = Field(default_factory=list)


class IdentifyRequest(BaseModel):
    # Base64-encoded JPEG (with or without the data: URL prefix).
    image_base64: str = Field(min_length=64)


class IdentifyResponse(BaseModel):
    artwork_id: Optional[str] = None  # None = "unknown / no confident match"
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""
