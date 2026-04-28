# Knowledge Base

Source documents and the ingester that chunks + embeds them into the vector
store the backend reads from at query time.

## Layout

```
KnowledgeBase/
  raw/                # Curated source docs (Markdown/txt). One per artwork + biography.
  chunks/             # JSONL output of the ingester. Generated; do not hand-edit.
  artworks.json       # Registry of artwork metadata (see schema below).
  ingest.py           # CLI: re-chunks raw/ and pushes to Chroma.
```

## artworks.json schema

```json
[
  {
    "id": "tamalada",
    "title": "Tamalada",
    "artist": "Carmen Lomas Garza",
    "year": "1987",
    "medium": "gouache on paper",
    "description": "Family scene of tamale-making in Kingsville, Texas."
  }
]
```

`id` is a snake_case slug. It must match:
- The basename of the source document in `raw/` (e.g. `tamalada.md`).
- The GameObject name of the artwork anchor in the Unity scene.
- The `artwork_id` the Unity client sends in the `/query` payload.

## Running ingest

```bash
# From the repo root
cd Backend && source venv/bin/activate
cd ../KnowledgeBase
python ingest.py
```

The ingester is **idempotent** — re-running it deletes existing chunks for each
source file before re-inserting. Safe to run after every edit.

If `raw/` is empty the ingester logs `no source documents found` and exits 0.
