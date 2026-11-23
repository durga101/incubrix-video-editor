"""
In-memory session store.

In production this would be backed by Redis or a database.
For this assessment, a module-level dict is sufficient.
"""
from __future__ import annotations

import threading
from typing import Optional

from engine.models import EditSession


_store: dict[str, EditSession] = {}
_lock = threading.Lock()


def create_session() -> EditSession:
    s = EditSession()
    with _lock:
        _store[s.session_id] = s
    return s


def get_session(session_id: str) -> Optional[EditSession]:
    with _lock:
        return _store.get(session_id)


def all_sessions() -> list[str]:
    with _lock:
        return list(_store.keys())


def delete_session(session_id: str) -> bool:
    with _lock:
        if session_id in _store:
            del _store[session_id]
            return True
        return False
