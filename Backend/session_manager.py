import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# NOTE: TTL eviction is out of scope for MVP. Sessions accumulate in memory until
# the process restarts. Add a sweeper before production.


@dataclass
class SessionState:
    session_id: str
    language: str
    visited_artworks: list[str] = field(default_factory=list)
    turns: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, language: str = "en") -> SessionState:
        session_id = uuid.uuid4().hex
        state = SessionState(session_id=session_id, language=language)
        self._sessions[session_id] = state
        return state

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def record_turn(self, session_id: str, artwork_id: Optional[str]) -> None:
        state = self._sessions.get(session_id)
        if state is None:
            return
        state.turns += 1
        if artwork_id and artwork_id not in state.visited_artworks:
            state.visited_artworks.append(artwork_id)
