"""One-shot artwork identification via Gemini Vision.

Visitor's phone camera captures a photo of the artwork in front of them.
We pass the image plus the registry of candidate artworks to Gemini and
ask which one it is. Cheap (one inference per identification, no Live
session), fast (~1-2s), and reliable enough to skip the manual picker
when the visitor is standing in front of a known piece.

Returns a small structured object:
    {id, confidence (0..1), reason}
where id is "unknown" if no candidate is a confident match.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Optional

from artwork_registry import ArtworkRegistry

log = logging.getLogger("identification")


IDENTIFY_PROMPT = """You are identifying a Carmen Lomas Garza artwork from a photo a visitor just took in the ASU Museum.

Match the photo against EXACTLY ONE of these candidate artworks (or "unknown" if none clearly match):

{candidates}

Rules:
- Use composition, palette, subject matter, and figures to match.
- Account for camera angle, glare, partial framing, and ambient lighting in the gallery.
- If you are not at least moderately confident, return "unknown".
- Do NOT invent an id that isn't in the candidate list.

Return ONLY a JSON object on a single line, no prose, no markdown:
{{"id": "<snake_case_id_or_unknown>", "confidence": <0.0..1.0>, "reason": "<one short sentence>"}}
"""


@dataclass
class IdentificationResult:
    artwork_id: Optional[str]  # None if "unknown"
    confidence: float
    reason: str


def _format_candidates(registry: ArtworkRegistry) -> str:
    lines = []
    for a in registry.all():
        bits = [f"id: {a.id}", f"title: {a.title}"]
        if a.year:
            bits.append(f"year: {a.year}")
        if a.medium:
            bits.append(f"medium: {a.medium}")
        if a.description:
            bits.append(f"description: {a.description}")
        lines.append(" · ".join(bits))
    return "\n".join(f"- {line}" for line in lines)


def identify_artwork(
    *,
    api_key: str,
    model: str,
    registry: ArtworkRegistry,
    image_jpeg_bytes: bytes,
) -> IdentificationResult:
    """Send the image + candidate list to Gemini Vision and parse the JSON
    reply. Imports google-genai lazily so the rest of the backend can run
    in unit tests without the SDK installed.
    """
    from google import genai
    from google.genai import types as gtypes

    candidates = _format_candidates(registry)
    prompt = IDENTIFY_PROMPT.format(candidates=candidates)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[
            gtypes.Content(
                role="user",
                parts=[
                    gtypes.Part(text=prompt),
                    gtypes.Part(
                        inline_data=gtypes.Blob(
                            mime_type="image/jpeg", data=image_jpeg_bytes
                        )
                    ),
                ],
            )
        ],
        config=gtypes.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text = (response.text or "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log.warning("identify: model returned non-JSON: %r", text[:200])
        return IdentificationResult(
            artwork_id=None, confidence=0.0, reason="couldn't parse model reply"
        )

    raw_id = (parsed.get("id") or "").strip().lower()
    confidence = float(parsed.get("confidence") or 0.0)
    reason = (parsed.get("reason") or "").strip()

    # Defense in depth: only accept ids that actually exist in the registry.
    artwork_id: Optional[str]
    if raw_id and raw_id != "unknown" and registry.exists(raw_id):
        artwork_id = raw_id
    else:
        artwork_id = None

    return IdentificationResult(
        artwork_id=artwork_id,
        confidence=max(0.0, min(1.0, confidence)),
        reason=reason or ("no confident match" if artwork_id is None else ""),
    )


def decode_b64_image(image_b64: str) -> bytes:
    """Strip a possible 'data:image/jpeg;base64,' prefix and b64-decode."""
    if "," in image_b64 and image_b64.lstrip().startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    return base64.b64decode(image_b64)
