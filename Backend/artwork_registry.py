import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Artwork(BaseModel):
    id: str
    title: str
    artist: str = "Carmen Lomas Garza"
    year: Optional[str] = None
    medium: Optional[str] = None
    description: Optional[str] = None


class ArtworkRegistry:
    def __init__(self, source: Path):
        self._source = source
        self._by_id: dict[str, Artwork] = {}
        self._load()

    def _load(self) -> None:
        if not self._source.exists():
            self._by_id = {}
            return
        raw = json.loads(self._source.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(
                f"{self._source} must contain a JSON array of artwork objects"
            )
        self._by_id = {item["id"]: Artwork(**item) for item in raw}

    def reload(self) -> None:
        self._load()

    def get(self, artwork_id: str) -> Optional[Artwork]:
        return self._by_id.get(artwork_id)

    def exists(self, artwork_id: str) -> bool:
        return artwork_id in self._by_id

    def all(self) -> list[Artwork]:
        return list(self._by_id.values())
