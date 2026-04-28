import hashlib
from pathlib import Path
from typing import Optional

import httpx


class TTSService:
    def __init__(
        self,
        api_key: str,
        voice_id_en: str,
        voice_id_es: str,
        model_id: str,
        cache_dir: Path,
    ):
        self._api_key = api_key
        self._voices = {"en": voice_id_en, "es": voice_id_es}
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, text: str, language: str, voice_id: str) -> str:
        h = hashlib.sha256()
        h.update(self._model_id.encode())
        h.update(b"|")
        h.update(voice_id.encode())
        h.update(b"|")
        h.update(language.encode())
        h.update(b"|")
        h.update(text.encode())
        return h.hexdigest()

    def cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.mp3"

    def synthesize(self, text: str, language: str = "en") -> Optional[str]:
        """Return a relative URL `/audio/{key}.mp3` for the synthesized clip,
        or None if synthesis is unavailable (no API key / no voice configured).
        """
        voice_id = self._voices.get(language) or self._voices.get("en")
        if not (self._api_key and voice_id and text.strip()):
            return None

        key = self._cache_key(text, language, voice_id)
        path = self.cache_path(key)
        if not path.exists():
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": self._api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": self._model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.7},
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                path.write_bytes(resp.content)
        return f"/audio/{key}.mp3"
