"""Session persistence: one folder per session under DATA_DIR with state.json + generated files."""
from __future__ import annotations

import json
import os
import uuid

from . import config
from .models import SessionState


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def session_dir(sid: str) -> str:
    d = os.path.join(config.DATA_DIR, "sessions", sid)
    os.makedirs(d, exist_ok=True)
    return d


def save(state: SessionState) -> None:
    with open(os.path.join(session_dir(state.id), "state.json"), "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=1))


def load(sid: str) -> SessionState:
    p = os.path.join(session_dir(sid), "state.json")
    if not os.path.exists(p):
        raise KeyError(sid)
    with open(p, encoding="utf-8") as f:
        return SessionState.model_validate_json(f.read())


def version_paths(sid: str, version: int) -> tuple[str, str]:
    d = session_dir(sid)
    return os.path.join(d, f"resume_v{version}.docx"), os.path.join(d, f"resume_v{version}.pdf")


def write_json(sid: str, name: str, data) -> None:
    with open(os.path.join(session_dir(sid), name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
