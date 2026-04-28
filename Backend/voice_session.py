"""Bridge between a browser WebSocket and the Gemini Live API.

The browser sends 16kHz PCM16 mono mic chunks plus a one-shot setup message
declaring the current artwork. We open a Live session pinned to that
artwork (system instruction names it; tool calls auto-filter retrieval).
Audio out is 24kHz PCM16 mono — streamed back to the browser as raw bytes.

Tool calls for `retrieve_chunks` are answered locally against the same
Chroma store + retrieval rules as the Anthropic /query path.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

from artwork_registry import ArtworkRegistry
from retrieval import retrieve
from vector_store import VectorStore

log = logging.getLogger("voice_session")
if not log.handlers:
    # Attach to root so uvicorn picks it up at startup-set level. INFO so
    # we can see turn boundaries during development without --log-level debug.
    log.setLevel(logging.INFO)

SYSTEM_INSTRUCTION = """You are a warm, knowledgeable museum educator guiding a visitor through the Carmen Lomas Garza exhibition at the ASU Museum.

The visitor is currently in front of: {artwork_line}.

Speak conversationally — short, clear sentences, the way a real educator would speak aloud. Two to four sentences per turn unless the visitor asks for more depth. You can pause, breathe, and respond to interruptions naturally.

Ground every factual claim in retrieved context. Whenever the visitor asks about an artwork's meaning, history, technique, or the artist herself, call the `retrieve_chunks` tool first with a focused query, then weave the retrieved facts into your spoken answer. If retrieval returns nothing relevant, say so honestly rather than improvising.

Pronounce Spanish words and names with care — *tamalada*, *curandera*, *cumpleaños*, *Carmen Lomas Garza* — and translate or paraphrase Spanish terms when they're likely unfamiliar.

Do not invent dates, dimensions, owners, or biographical details. If you're unsure, say "I'm not certain about that" rather than guess.
"""


RETRIEVE_TOOL = {
    "function_declarations": [
        {
            "name": "retrieve_chunks",
            "description": (
                "Retrieve curated knowledge-base passages about the current "
                "artwork or about Carmen Lomas Garza. Call this whenever the "
                "visitor asks about meaning, history, technique, biography, "
                "or cultural context, before composing your spoken answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A focused, specific question phrased in the "
                            "visitor's words or a paraphrase of it. Example: "
                            "'why is tamale-making significant in Tamalada'."
                        ),
                    }
                },
                "required": ["query"],
            },
        }
    ]
}


@dataclass
class VoiceSessionConfig:
    api_key: str
    model: str
    voice_name: str
    artwork_line: str  # already formatted, e.g. '"Tamalada" (1987, gouache on paper)'


def _artwork_line_for(registry: ArtworkRegistry, artwork_id: Optional[str]) -> str:
    if artwork_id and (a := registry.get(artwork_id)):
        return f'"{a.title}" ({a.year or "n.d."}, {a.medium or "unknown medium"})'
    return "the gallery (no specific artwork in focus yet)"


async def run_voice_session(
    *,
    ws,  # fastapi.WebSocket — typed loosely to avoid import here
    api_key: str,
    model: str,
    voice_name: str,
    store: VectorStore,
    registry: ArtworkRegistry,
) -> None:
    """Drive one browser <-> Gemini Live session to completion."""
    # Imported lazily so the rest of the backend boots without google-genai
    # installed (e.g. in CI / unit tests).
    from google import genai
    from google.genai import types as gtypes

    # 1. Read the setup handshake from the browser.
    raw = await ws.receive_text()
    setup = json.loads(raw)
    artwork_id: Optional[str] = setup.get("artwork_id")
    artwork_line = _artwork_line_for(registry, artwork_id)

    system_instruction = SYSTEM_INSTRUCTION.format(artwork_line=artwork_line)

    # Push-to-talk = manual VAD. We tell Gemini exactly when the visitor's
    # utterance starts and ends with activity_start / activity_end signals
    # below. Without this, Gemini's automatic VAD has to guess turn
    # boundaries and we have to send audio_stream_end=True on release —
    # which terminates the entire input stream after the first turn.
    config = gtypes.LiveConnectConfig(
        response_modalities=[gtypes.Modality.AUDIO],
        system_instruction=gtypes.Content(
            role="user", parts=[gtypes.Part(text=system_instruction)]
        ),
        speech_config=gtypes.SpeechConfig(
            voice_config=gtypes.VoiceConfig(
                prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        tools=[RETRIEVE_TOOL],
        output_audio_transcription=gtypes.AudioTranscriptionConfig(),
        realtime_input_config=gtypes.RealtimeInputConfig(
            automatic_activity_detection=gtypes.AutomaticActivityDetection(
                disabled=True,
            ),
        ),
    )

    client = genai.Client(api_key=api_key)

    async with client.aio.live.connect(model=model, config=config) as session:
        await ws.send_json({"type": "ready", "artwork_id": artwork_id})
        log.info("voice session ready (artwork=%s, model=%s)", artwork_id, model)

        turn_idx = 0
        chunk_count = 0

        async def pump_browser_to_gemini():
            """Forward mic audio + control messages from browser to Gemini.

            Push-to-talk turn boundaries:
              - {type: "start_turn"} → activity_start (visitor pressed button)
              - audio chunks         → relayed verbatim
              - {type: "end_turn"}   → activity_end (visitor released button)
            """
            nonlocal turn_idx, chunk_count
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    log.info("[turn %d] browser disconnected", turn_idx)
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    chunk_count += 1
                    await session.send_realtime_input(
                        audio=gtypes.Blob(
                            data=msg["bytes"], mime_type="audio/pcm;rate=16000"
                        )
                    )
                elif "text" in msg and msg["text"] is not None:
                    try:
                        ctrl = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    kind = ctrl.get("type")
                    if kind == "start_turn":
                        turn_idx += 1
                        chunk_count = 0
                        log.info("[turn %d] start_turn → activity_start", turn_idx)
                        await session.send_realtime_input(
                            activity_start=gtypes.ActivityStart()
                        )
                    elif kind == "end_turn":
                        log.info(
                            "[turn %d] end_turn → activity_end (after %d audio chunks)",
                            turn_idx,
                            chunk_count,
                        )
                        await session.send_realtime_input(
                            activity_end=gtypes.ActivityEnd()
                        )

        async def pump_gemini_to_browser():
            """Forward audio + tool calls + transcripts from Gemini to browser."""
            async for response in session.receive():
                # 1. Tool calls — handle locally, send response back.
                if response.tool_call is not None:
                    fn_responses = []
                    for fc in response.tool_call.function_calls:
                        if fc.name == "retrieve_chunks":
                            q = (fc.args or {}).get("query", "") or ""
                            log.info(
                                "[turn %d] tool_call retrieve_chunks(%r)",
                                turn_idx,
                                q,
                            )
                            result = retrieve(
                                store=store,
                                registry=registry,
                                query=q,
                                artwork_id=artwork_id,
                            )
                            payload = {"context": result.formatted_context}
                            await ws.send_json(
                                {
                                    "type": "tool_call",
                                    "name": fc.name,
                                    "query": q,
                                    "chunks": [c.chunk_id for c in result.chunks],
                                }
                            )
                        else:
                            payload = {
                                "error": f"unknown tool: {fc.name}"
                            }
                        fn_responses.append(
                            gtypes.FunctionResponse(
                                id=fc.id, name=fc.name, response=payload
                            )
                        )
                    await session.send_tool_response(function_responses=fn_responses)
                    continue

                sc = response.server_content
                if sc is None:
                    continue

                # 2. Audio out — stream the raw PCM to the browser.
                if sc.model_turn is not None:
                    for part in sc.model_turn.parts or []:
                        if part.inline_data and part.inline_data.data:
                            await ws.send_bytes(part.inline_data.data)

                # 3. Output transcript — send for on-screen display.
                if sc.output_transcription and sc.output_transcription.text:
                    await ws.send_json(
                        {
                            "type": "transcript",
                            "text": sc.output_transcription.text,
                        }
                    )

                if sc.turn_complete:
                    log.info("[turn %d] turn_complete", turn_idx)
                    await ws.send_json({"type": "turn_complete"})
                if getattr(sc, "interrupted", False):
                    log.info("[turn %d] interrupted by visitor", turn_idx)

        # Run both pumps concurrently. Whichever finishes first cancels the other.
        try:
            await asyncio.gather(
                pump_browser_to_gemini(),
                pump_gemini_to_browser(),
            )
        except Exception as exc:
            log.exception("voice session error: %s", exc)
            try:
                await ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass
