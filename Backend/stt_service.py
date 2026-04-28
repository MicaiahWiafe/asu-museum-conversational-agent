import base64
import io

from openai import OpenAI


class STTService:
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self._client = OpenAI(api_key=api_key) if api_key else None
        self._model = model

    def transcribe(self, audio_base64: str, language: str = "en") -> tuple[str, float]:
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        audio_bytes = base64.b64decode(audio_base64)
        buf = io.BytesIO(audio_bytes)
        # Whisper requires a filename to infer format. Unity sends 16-bit PCM WAV.
        buf.name = "audio.wav"

        result = self._client.audio.transcriptions.create(
            file=buf,
            model=self._model,
            language=language,
            response_format="json",
        )
        text = (getattr(result, "text", "") or "").strip()
        # whisper-1 doesn't return per-utterance confidence; we report a fixed
        # high baseline so the contract holds. Swap for verbose_json + avg
        # logprob averaging if confidence becomes load-bearing.
        return text, 0.95
