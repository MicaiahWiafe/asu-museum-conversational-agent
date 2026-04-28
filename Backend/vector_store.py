from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import chromadb
from chromadb.utils import embedding_functions


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str
    artwork_id: Optional[str] = None


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source: str
    artwork_id: Optional[str]
    score: float


class VectorStore(Protocol):
    def add_chunks(self, chunks: list[Chunk]) -> None: ...
    def query(
        self,
        text: str,
        k: int = 5,
        artwork_id_filter: Optional[str] = None,
    ) -> list[RetrievedChunk]: ...
    def delete_by_source(self, source: str) -> None: ...
    def count(self) -> int: ...


class ChromaStore:
    def __init__(
        self,
        persist_dir: Path,
        collection: str,
        embedding_model: str,
    ):
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )
        self._collection = self._client.get_or_create_collection(
            name=collection,
            embedding_function=self._embedder,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {"source": c.source, "artwork_id": c.artwork_id or ""}
                for c in chunks
            ],
        )

    def query(
        self,
        text: str,
        k: int = 5,
        artwork_id_filter: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        where = {"artwork_id": artwork_id_filter} if artwork_id_filter else None
        result = self._collection.query(
            query_texts=[text],
            n_results=k,
            where=where,
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        out: list[RetrievedChunk] = []
        for i, doc, meta, dist in zip(ids, docs, metas, dists):
            score = 1.0 - float(dist) if dist is not None else 0.0
            out.append(
                RetrievedChunk(
                    chunk_id=i,
                    text=doc,
                    source=(meta or {}).get("source", "unknown"),
                    artwork_id=(meta or {}).get("artwork_id") or None,
                    score=score,
                )
            )
        return out

    def delete_by_source(self, source: str) -> None:
        self._collection.delete(where={"source": source})

    def count(self) -> int:
        return self._collection.count()
