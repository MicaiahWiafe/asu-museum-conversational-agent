#!/usr/bin/env python3
"""Chunk every document in ./raw and push to the configured vector store.

Usage:
    python ingest.py [--dry-run]

Idempotent: re-running deletes existing chunks for each source file before
re-inserting.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
BACKEND_DIR = REPO_ROOT / "Backend"
sys.path.insert(0, str(BACKEND_DIR))

# Imported lazily after sys.path manipulation.
from config import get_settings  # noqa: E402
from vector_store import Chunk, ChromaStore  # noqa: E402

CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
# Approximate token count via 4 chars/token. Avoids a tokenizer dep.
CHARS_PER_TOKEN = 4
TARGET_CHARS = CHUNK_TARGET_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN


def chunk_text(text: str) -> list[str]:
    """Paragraph-aware sliding window. Preserves paragraph boundaries unless a
    single paragraph exceeds the target, in which case it character-slices."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(p) > TARGET_CHARS:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(p), TARGET_CHARS - OVERLAP_CHARS):
                chunks.append(p[i : i + TARGET_CHARS])
            continue

        if len(buf) + len(p) + 2 > TARGET_CHARS and buf:
            chunks.append(buf)
            tail = buf[-OVERLAP_CHARS:] if OVERLAP_CHARS < len(buf) else buf
            buf = (tail + "\n\n" + p).strip()
        else:
            buf = (buf + "\n\n" + p).strip() if buf else p

    if buf:
        chunks.append(buf)
    return chunks


def derive_artwork_id(filename: str, registry_ids: set[str]) -> str | None:
    stem = Path(filename).stem
    if stem == "artist_biography":
        return None
    return stem if stem in registry_ids else None


def load_registry_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"] for item in data} if isinstance(data, list) else set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    raw_dir = THIS_DIR / "raw"
    chunks_dir = THIS_DIR / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(
        p
        for p in (list(raw_dir.glob("*.md")) + list(raw_dir.glob("*.txt")))
        if p.name.lower() != "readme.md"
    )
    if not sources:
        print("no source documents found in", raw_dir)
        return 0

    registry_ids = load_registry_ids(settings.artworks_json_path)
    if not registry_ids:
        print(
            f"warning: {settings.artworks_json_path} is empty or missing — "
            "artwork-scoped retrieval will be limited to artist_biography."
        )

    store: ChromaStore | None = None
    if not args.dry_run:
        store = ChromaStore(
            persist_dir=settings.chroma_persist_path,
            collection=settings.chroma_collection,
            embedding_model=settings.embedding_model,
        )

    total_chunks = 0
    for src in sources:
        text = src.read_text(encoding="utf-8")
        pieces = chunk_text(text)
        artwork_id = derive_artwork_id(src.name, registry_ids)

        chunk_objs = [
            Chunk(
                chunk_id=f"{src.stem}::{i:04d}",
                text=piece,
                source=src.name,
                artwork_id=artwork_id,
            )
            for i, piece in enumerate(pieces)
        ]

        # Persist a JSONL snapshot for inspection.
        out_path = chunks_dir / f"{src.stem}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for c in chunk_objs:
                f.write(
                    json.dumps(
                        {
                            "chunk_id": c.chunk_id,
                            "source": c.source,
                            "artwork_id": c.artwork_id,
                            "text": c.text,
                        }
                    )
                    + "\n"
                )

        if store is not None:
            store.delete_by_source(src.name)
            store.add_chunks(chunk_objs)

        total_chunks += len(chunk_objs)
        print(f"  {src.name}: {len(chunk_objs)} chunks (artwork_id={artwork_id})")

    print(f"done. {total_chunks} chunks across {len(sources)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
