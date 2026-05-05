"""Bridge between a browser WebSocket and the Gemini Live API.

The browser sends 16kHz PCM16 mono mic chunks plus a one-shot setup message
declaring the current artwork. We open a Live session pinned to that
artwork (system instruction names it; tool calls auto-filter retrieval).
Audio out is 24kHz PCM16 mono — streamed back to the browser as raw bytes.

Tool calls for `retrieve_chunks` are answered locally against the same
Chroma store + retrieval rules as the Anthropic /query path.

Multi-turn invariants:
  * The Gemini Live session persists for the lifetime of the browser
    WebSocket. Conversation history (every prior user audio + every prior
    model response) is part of the session's context, so follow-up
    questions like "tell me more" or "how does that compare?" naturally
    work for VOICE turns.
  * Auto VAD. The model decides where utterances begin and end based on
    silence detection. Manual VAD with activity_start/activity_end
    signals was tried first (cleaner push-to-talk semantics) but
    interacted badly with the preview models — duplicate signals could
    crash the session with a keepalive ping timeout.
  * A 10-second backend → browser heartbeat keeps the WebSocket alive
    through any idle-timeout proxies (notably Cloudflare quick tunnels,
    which 524 idle WS after ~100s).

KNOWN ISSUES:
  * Multi-turn TEXT within a single session is flaky as of Gemini Live's
    current preview models (gemini-2.5-flash-native-audio-latest and
    gemini-3.1-flash-live-preview, May 2026). Turn 1 text via
    send_realtime_input(text=...) works; turn 2 text in the same session
    sometimes never receives a response. Voice multi-turn is fine. As a
    workaround for now, the frontend can close + reopen the WebSocket on
    each text submission (sacrificing per-text memory but guaranteeing
    a response). Voice barge-in to text or vice-versa is also rough.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from artwork_registry import ArtworkRegistry
from retrieval import retrieve
from vector_store import VectorStore

log = logging.getLogger("voice_session")
log.setLevel(logging.INFO)
# Propagate up to uvicorn's root logger so messages appear alongside the
# request log lines. Without an explicit handler the logger's INFO records
# would be filtered by the default WARNING root level.
if not log.handlers and not any(
    isinstance(h, logging.StreamHandler) for h in logging.getLogger().handlers
):
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [voice_session] %(message)s"))
    log.addHandler(_h)
log.propagate = True


HEARTBEAT_INTERVAL_SEC = 10.0


SYSTEM_INSTRUCTION = """You are a warm, knowledgeable museum educator guiding a visitor through the Carmen Lomas Garza exhibition at the ASU Museum.

The visitor is currently in front of: {artwork_line}.

Speak conversationally — short, clear sentences, the way a real educator would speak aloud. Two to four sentences per turn unless the visitor asks for more depth. You can pause, breathe, and respond to interruptions naturally.

LANGUAGE: Respond in the language the visitor uses. If they speak or type in Spanish, answer in Spanish. English in, English out. The same applies to French, Portuguese, Mandarin, or any other language Gemini supports — match the visitor's language for that turn. If they switch languages mid-conversation, switch with them on the next turn. When the visitor uses a Spanish word or phrase inside an otherwise-English sentence (very common at this exhibition), keep the Spanish word and translate or gloss it briefly the first time.

INPUT MODE: The visitor can either speak (push-to-talk) or type. Treat typed and spoken questions identically; both should get a spoken answer in the same language as the input.

CONTINUITY: You are mid-conversation. Any prior turns you can see — questions the visitor asked and answers you gave — happened moments ago and are part of this same flowing discussion. Treat each new utterance as a follow-up. When the visitor says "tell me more about that", "what about it", "how does this compare to what we just discussed", or "earlier you mentioned…", pick up the thread without asking them to repeat themselves. Don't reintroduce the painting or the artist on every turn — assume they're still in front of the same work and you've already been chatting. Vary your phrasing across turns; if you used a particular word or framing in the last answer, try a different angle this time so the conversation doesn't feel repetitive.

GROUNDING: Ground every factual claim in retrieved context. Whenever the visitor asks about an artwork's meaning, history, technique, or the artist herself, call the `retrieve_chunks` tool first with a focused query (English query is fine even if the visitor asks in another language — the knowledge base is in English). Weave the retrieved facts into your spoken answer in the visitor's language. If retrieval returns nothing relevant, say so honestly rather than improvising.

PRONUNCIATION: Pronounce Spanish words and names with care — *tamalada*, *curandera*, *cumpleaños*, *Carmen Lomas Garza* — and translate or paraphrase Spanish terms when they're likely unfamiliar to a non-Spanish speaker.

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

    raw = await ws.receive_text()
    setup = json.loads(raw)
    artwork_id: Optional[str] = setup.get("artwork_id")
    artwork_line = _artwork_line_for(registry, artwork_id)
    system_instruction = SYSTEM_INSTRUCTION.format(artwork_line=artwork_line)

    # Conversation history sent by the client. Each item is
    # {role: "user" | "model", text: "..."}. We use this to PRIME the
    # fresh Gemini Live session so the visitor doesn't feel like every
    # turn starts from scratch. Capped at the most recent 8 entries to
    # keep priming cheap.
    history_in: list[dict] = setup.get("history") or []
    history_in = history_in[-8:]

    # Auto VAD (default). Earlier we tried manual VAD with activity_start/
    # activity_end signals because push-to-talk has crisp turn boundaries,
    # but that path crashed the Gemini Live session on the SECOND turn
    # whenever text and voice were mixed (the SDK explicitly warns against
    # interleaving send_client_content with send_realtime_input). Auto VAD
    # commits a turn after ~500ms of silence at the end of the visitor's
    # utterance — slightly more latency than manual VAD, but rock-solid
    # multi-turn behavior across both modalities.
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
        # Transcribe the visitor's voice input too. The frontend uses
        # this to thread the conversation back into history for the next
        # session, so voice turns can build on prior voice turns
        # naturally.
        input_audio_transcription=gtypes.AudioTranscriptionConfig(),
    )

    client = genai.Client(api_key=api_key)

    # Mutable per-turn timing state shared by the pumps.
    state = {
        "turn_idx": 0,
        "chunk_count": 0,
        "released_at": None,  # monotonic timestamp at activity_end
        "first_byte_at": None,
        "first_tool_call_at": None,
    }

    async with client.aio.live.connect(model=model, config=config) as session:
        # Prime the session with prior conversation so the visitor's new
        # turn lands in a continuing thread, not a cold start. Each
        # historical entry is sent as a non-committing client_content
        # turn (turn_complete=False); the actual new input below
        # commits and triggers generation.
        for entry in history_in:
            role = "model" if entry.get("role") == "model" else "user"
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            try:
                await session.send_client_content(
                    turns=gtypes.Content(
                        role=role, parts=[gtypes.Part(text=text)]
                    ),
                    turn_complete=False,
                )
            except Exception as exc:
                log.warning("history priming failed: %s", exc)
                break
        if history_in:
            log.info("primed session with %d history turn(s)", len(history_in))

        await ws.send_json({"type": "ready", "artwork_id": artwork_id})
        log.info("voice session ready (artwork=%s, model=%s)", artwork_id, model)

        async def pump_browser_to_gemini():
            """Forward mic audio + control messages from browser to Gemini."""
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    log.info("[turn %d] browser disconnected", state["turn_idx"])
                    return
                if "bytes" in msg and msg["bytes"] is not None:
                    state["chunk_count"] += 1
                    try:
                        await session.send_realtime_input(
                            audio=gtypes.Blob(
                                data=msg["bytes"], mime_type="audio/pcm;rate=16000"
                            )
                        )
                    except Exception as exc:
                        log.exception(
                            "[turn %d] send_realtime_input(audio) failed: %s",
                            state["turn_idx"],
                            exc,
                        )
                        raise
                elif "text" in msg and msg["text"] is not None:
                    try:
                        ctrl = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    kind = ctrl.get("type")
                    if kind == "start_turn":
                        # Auto VAD: no activity_start needed — Gemini detects
                        # speech on its own. Track the boundary for logging
                        # and per-turn timing only.
                        state["turn_idx"] += 1
                        state["chunk_count"] = 0
                        state["released_at"] = None
                        state["first_byte_at"] = None
                        state["first_tool_call_at"] = None
                        log.info("[turn %d] start_turn (push)", state["turn_idx"])
                    elif kind == "end_turn":
                        # Visitor released the button. Auto VAD's silence
                        # detection commits ~500ms after we stop sending
                        # audio chunks (which the browser already did when
                        # MicCapture.stop ran).
                        state["released_at"] = time.monotonic()
                        log.info(
                            "[turn %d] end_turn (release, after %d audio chunks)",
                            state["turn_idx"],
                            state["chunk_count"],
                        )
                    elif kind == "text_turn":
                        text = (ctrl.get("text") or "").strip()
                        if not text:
                            continue
                        state["turn_idx"] += 1
                        state["chunk_count"] = 0
                        state["released_at"] = time.monotonic()
                        state["first_byte_at"] = None
                        state["first_tool_call_at"] = None
                        log.info(
                            "[turn %d] text_turn (%d chars): %r",
                            state["turn_idx"],
                            len(text),
                            text[:120] + ("…" if len(text) > 120 else ""),
                        )
                        # send_realtime_input(text=...) is the path that
                        # reliably triggers generation. send_client_content
                        # silently fails to produce output on the
                        # gemini-3.1-flash-live-preview model and on
                        # gemini-2.5-flash-native-audio-latest after a
                        # tool_call cycle. Multi-turn TEXT in the SAME
                        # session is currently flaky regardless of method —
                        # see KNOWN ISSUES at the top of this file.
                        await session.send_realtime_input(text=text)

        async def pump_gemini_to_browser():
            """Forward audio + tool calls + transcripts from Gemini to browser."""
            async for response in session.receive():
                turn_idx = state["turn_idx"]

                if response.tool_call is not None:
                    if state["first_tool_call_at"] is None:
                        state["first_tool_call_at"] = time.monotonic()
                        if state["released_at"]:
                            ms = (
                                state["first_tool_call_at"] - state["released_at"]
                            ) * 1000
                            log.info(
                                "[turn %d] first tool_call latency: %.0f ms",
                                turn_idx,
                                ms,
                            )

                    fn_responses = []
                    for fc in response.tool_call.function_calls:
                        if fc.name == "retrieve_chunks":
                            q = (fc.args or {}).get("query", "") or ""
                            t0 = time.monotonic()
                            result = retrieve(
                                store=store,
                                registry=registry,
                                query=q,
                                artwork_id=artwork_id,
                            )
                            log.info(
                                "[turn %d] retrieve_chunks(%r) → %d chunks in %.0f ms",
                                turn_idx,
                                q,
                                len(result.chunks),
                                (time.monotonic() - t0) * 1000,
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
                            payload = {"error": f"unknown tool: {fc.name}"}
                        fn_responses.append(
                            gtypes.FunctionResponse(
                                id=fc.id, name=fc.name, response=payload
                            )
                        )
                    await session.send_tool_response(function_responses=fn_responses)
                    continue

                sc = response.server_content
                if sc is None:
                    # GoAway / SessionResumptionUpdate / etc. Log and keep going.
                    log.debug(
                        "[turn %d] response with no server_content (likely a control frame)",
                        turn_idx,
                    )
                    continue

                if sc.model_turn is not None:
                    for part in sc.model_turn.parts or []:
                        if part.inline_data and part.inline_data.data:
                            if state["first_byte_at"] is None:
                                state["first_byte_at"] = time.monotonic()
                                if state["released_at"]:
                                    ms = (
                                        state["first_byte_at"] - state["released_at"]
                                    ) * 1000
                                    log.info(
                                        "[turn %d] first audio byte latency: %.0f ms",
                                        turn_idx,
                                        ms,
                                    )
                            await ws.send_bytes(part.inline_data.data)

                if sc.output_transcription and sc.output_transcription.text:
                    await ws.send_json(
                        {
                            "type": "transcript",
                            "text": sc.output_transcription.text,
                        }
                    )

                if (
                    getattr(sc, "input_transcription", None)
                    and sc.input_transcription.text
                ):
                    # The visitor's voice, transcribed. Frontend folds
                    # this into the conversation history for the next
                    # session's priming.
                    await ws.send_json(
                        {
                            "type": "input_transcript",
                            "text": sc.input_transcription.text,
                        }
                    )

                if getattr(sc, "interrupted", False):
                    log.info("[turn %d] interrupted by visitor barge-in", turn_idx)

                if getattr(sc, "generation_complete", False):
                    log.info("[turn %d] generation_complete", turn_idx)

                if sc.turn_complete:
                    total_ms = (
                        (time.monotonic() - state["released_at"]) * 1000
                        if state["released_at"]
                        else 0.0
                    )
                    log.info(
                        "[turn %d] turn_complete (total %.0f ms from release)",
                        turn_idx,
                        total_ms,
                    )
                    await ws.send_json({"type": "turn_complete"})

        async def heartbeat():
            """Server-side keepalive. Cloudflare quick tunnels (and most HTTP
            proxies) close idle WebSockets after ~100s; periodic JSON frames
            keep the connection warm without polluting the audio stream.
            """
            while True:
                try:
                    await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
                    await ws.send_json({"type": "heartbeat"})
                except Exception:
                    return

        try:
            await asyncio.gather(
                pump_browser_to_gemini(),
                pump_gemini_to_browser(),
                heartbeat(),
            )
        except Exception as exc:
            log.exception("voice session error: %s", exc)
            try:
                await ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass
