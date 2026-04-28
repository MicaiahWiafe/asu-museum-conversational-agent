from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

from artwork_registry import ArtworkRegistry
from models import SourceChunk
from retrieval import retrieve
from vector_store import VectorStore

SYSTEM_PROMPT_TEMPLATE = """You are a knowledgeable and warm gallery guide for the Carmen Lomas Garza exhibition.
You answer questions about the artworks, the artist's life, her techniques, and the
cultural context of her work. You speak in {language_name}.

The visitor is currently looking at: {artwork_line}
They have already visited: {visited_line}.

Answer conversationally in 2-4 sentences. Ground your answer in the provided context.
If you don't know something, say so honestly rather than speculating.

Context:
{retrieved_chunks}
"""

LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


@dataclass
class RagResult:
    response_text: str
    source_chunks: list[SourceChunk]


class RagPipeline:
    def __init__(
        self,
        vector_store: VectorStore,
        registry: ArtworkRegistry,
        anthropic_client: Anthropic,
        model: str,
    ):
        self._store = vector_store
        self._registry = registry
        self._client = anthropic_client
        self._model = model

    def _build_context(
        self, query: str, artwork_id: Optional[str]
    ) -> tuple[str, list]:
        result = retrieve(
            store=self._store,
            registry=self._registry,
            query=query,
            artwork_id=artwork_id,
        )
        return result.formatted_context, result.chunks

    def _build_system_prompt(
        self,
        language: str,
        artwork_id: Optional[str],
        visited: list[str],
        retrieved_text: str,
    ) -> str:
        if artwork_id and (art := self._registry.get(artwork_id)):
            artwork_line = f'"{art.title}" ({art.year or "n.d."}, {art.medium or "unknown medium"}).'
        else:
            artwork_line = "(no specific artwork — general gallery question)."
        visited_titles = []
        for aid in visited:
            art = self._registry.get(aid)
            visited_titles.append(art.title if art else aid)
        visited_line = ", ".join(visited_titles) if visited_titles else "nothing yet"

        return SYSTEM_PROMPT_TEMPLATE.format(
            language_name=LANGUAGE_NAMES.get(language, "English"),
            artwork_line=artwork_line,
            visited_line=visited_line,
            retrieved_chunks=retrieved_text,
        )

    def answer(
        self,
        query: str,
        artwork_id: Optional[str],
        language: str,
        visited: list[str],
    ) -> RagResult:
        retrieved_text, retrieved = self._build_context(query, artwork_id)
        system_prompt = self._build_system_prompt(
            language=language,
            artwork_id=artwork_id,
            visited=visited,
            retrieved_text=retrieved_text,
        )

        # Prompt caching on the system block: stable instructions + retrieved
        # context get cached so repeat queries against the same artwork reuse
        # the cached prefix. The user message (per-turn query) stays uncached.
        message = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": query}],
        )

        text_parts = [
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ]
        response_text = "".join(text_parts).strip()

        sources = [
            SourceChunk(chunk_id=c.chunk_id, source=c.source, score=round(c.score, 4))
            for c in retrieved
        ]
        return RagResult(response_text=response_text, source_chunks=sources)
