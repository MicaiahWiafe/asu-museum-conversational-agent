"""Retrieval-only logic. Shared between the Anthropic /query path (Quest) and
the Gemini Live tool-call path (mobile).

The grounding rules (top-k filtered by artwork + forced bio chunk + char
budget) live here so both clients see the same chunks for the same query.
"""
from dataclasses import dataclass
from typing import Optional

from artwork_registry import ArtworkRegistry
from vector_store import RetrievedChunk, VectorStore

# Approximate token cap on retrieved-chunk content. 4 chars/token estimate.
CONTEXT_CHAR_BUDGET = 1500 * 4


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    formatted_context: str


def retrieve(
    *,
    store: VectorStore,
    registry: ArtworkRegistry,
    query: str,
    artwork_id: Optional[str],
    k: int = 5,
) -> RetrievalResult:
    """Top-k chunks filtered by artwork_id where present, plus one forced bio
    chunk if no biography chunk made it into the artwork-filtered slice.
    Truncated to CONTEXT_CHAR_BUDGET. Order preserved from Chroma's ranking.
    """
    if artwork_id and not registry.exists(artwork_id):
        artwork_id = None  # silently fall back to unfiltered

    retrieved = store.query(query, k=k, artwork_id_filter=artwork_id)

    bio_present = any("artist_biography" in c.source for c in retrieved)
    if not bio_present:
        # Query wider unfiltered, then pick the first chunk that's actually
        # from the biography file. k=1 isn't enough — top results often come
        # from the same artwork file as the query.
        bio_results = store.query(query, k=8, artwork_id_filter=None)
        for b in bio_results:
            if "artist_biography" in b.source and not any(
                r.chunk_id == b.chunk_id for r in retrieved
            ):
                # Insert AFTER the top artwork hit so the bio survives the
                # char-budget truncation below.
                insert_at = 1 if retrieved else 0
                retrieved.insert(insert_at, b)
                break

    used = 0
    kept: list[RetrievedChunk] = []
    for c in retrieved:
        if used + len(c.text) > CONTEXT_CHAR_BUDGET and kept:
            break
        kept.append(c)
        used += len(c.text)

    formatted = "\n\n---\n\n".join(
        f"[{c.source}]\n{c.text}" for c in kept
    ) or "(no context retrieved)"

    return RetrievalResult(chunks=kept, formatted_context=formatted)
