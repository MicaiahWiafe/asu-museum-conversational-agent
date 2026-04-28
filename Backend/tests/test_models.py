import pytest
from pydantic import ValidationError

from models import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SessionStartRequest,
    SessionStartResponse,
    SourceChunk,
    TranscribeRequest,
    TranscribeResponse,
)


def test_query_request_roundtrip():
    payload = {
        "session_id": "abc",
        "artwork_id": "tamalada",
        "query_text": "Tell me about this scene.",
        "language": "en",
        "visited_artworks": ["sandia"],
    }
    req = QueryRequest(**payload)
    assert req.model_dump() == payload


def test_query_request_defaults():
    req = QueryRequest(session_id="s", query_text="hi")
    assert req.language == "en"
    assert req.visited_artworks == []
    assert req.artwork_id is None


def test_query_response_roundtrip():
    resp = QueryResponse(
        response_text="hello",
        audio_url="/audio/abc.mp3",
        source_chunks=[SourceChunk(chunk_id="c1", source="bio.md", score=0.91)],
        session_id="s1",
    )
    parsed = QueryResponse(**resp.model_dump())
    assert parsed == resp


def test_transcribe_models():
    req = TranscribeRequest(audio_base64="AA==", language="en")
    assert req.language == "en"
    resp = TranscribeResponse(transcript="hi", confidence=0.5)
    assert resp.confidence == 0.5


def test_transcribe_confidence_bounds():
    with pytest.raises(ValidationError):
        TranscribeResponse(transcript="x", confidence=1.5)


def test_session_models():
    assert SessionStartRequest().language == "en"
    s = SessionStartResponse(session_id="abc")
    assert s.session_id == "abc"


def test_health_defaults():
    h = HealthResponse()
    assert h.status == "ok"
    assert h.vector_store == "ok"
    assert h.llm == "ok"
