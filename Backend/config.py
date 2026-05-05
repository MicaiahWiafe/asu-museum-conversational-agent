from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


def _anchor(p: str) -> Path:
    """Anchor a relative path to Backend/. Absolute paths pass through.
    This makes the default `./chroma_db` mean Backend/chroma_db whether the
    process was started from Backend/ (uvicorn) or KnowledgeBase/ (ingest.py).
    """
    path = Path(p)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    openai_api_key: str = ""
    whisper_model: str = "whisper-1"

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id_en: str = ""
    elevenlabs_voice_id_es: str = ""
    elevenlabs_model_id: str = "eleven_turbo_v2_5"

    # Gemini Live (mobile path)
    gemini_api_key: str = ""
    # Native-audio model — Gemini generates audio tokens directly for warmer
    # prosody than half-cascade. `-latest` auto-tracks the newest preview.
    gemini_live_model: str = "gemini-2.5-flash-native-audio-latest"
    gemini_voice_name: str = "Aoede"  # warm, female, educator-leaning
    # Vision model for one-shot artwork identification from a phone-camera
    # photo. Cheap + fast; not the Live model.
    gemini_vision_model: str = "gemini-2.5-flash"

    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "carmen_lomas_garza"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    artworks_json: str = "../KnowledgeBase/artworks.json"

    tts_cache_dir: str = "./tts_cache"

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tts_cache_path(self) -> Path:
        return _anchor(self.tts_cache_dir)

    @property
    def chroma_persist_path(self) -> Path:
        return _anchor(self.chroma_persist_dir)

    @property
    def artworks_json_path(self) -> Path:
        return _anchor(self.artworks_json)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
