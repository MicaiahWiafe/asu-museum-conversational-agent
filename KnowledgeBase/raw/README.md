# Knowledge Base — raw documents

Drop curated source documents here, one per artwork plus an artist biography.

## File naming

Use snake_case slugs that match the `id` field in `../artworks.json` and the
GameObject names of the artwork anchors in the Unity scene.

```
raw/
  artist_biography.md
  tamalada.md
  sandia.md
  cumpleanos_de_lala_y_tudi.md
```

## Format

Plain Markdown or `.txt`. The ingester chunks by paragraph (target ~500 tokens
with 50-token overlap). Section headings (`#`, `##`) are preserved as natural
break points.

Avoid:
- HTML, footnotes, or JSON inside the document body — they survive chunking but
  pollute the retrieved context.
- Front matter — it gets embedded as-is.

## Re-ingesting

After editing or adding files, run:

```bash
python ../ingest.py
```

The ingester is idempotent: chunks for a given source file are deleted and
re-inserted on every run.
