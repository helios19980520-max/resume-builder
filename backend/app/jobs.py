"""Tiny in-process background job runner with progress messages (polled by the UI)."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"  # running | done | error
    messages: list[str] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def progress(self, msg: str):
        self.messages.append(msg)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status, "messages": self.messages,
                "result": self.result, "error": self.error,
                "elapsed": round((self.finished or time.time()) - self.started, 1)}


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def start(kind: str, fn: Callable[[Job], Any]) -> Job:
    job = Job(id=uuid.uuid4().hex[:10], kind=kind)
    with _lock:
        _jobs[job.id] = job

    def run():
        try:
            job.result = fn(job)
            job.status = "done"
        except Exception as e:  # noqa
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.messages.append("Failed: " + job.error)
            traceback.print_exc()
        finally:
            job.finished = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)
