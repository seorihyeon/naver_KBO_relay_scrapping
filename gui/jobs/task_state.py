from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import queue
import threading
from typing import Any


class JobCancelledError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobLogEntry:
    level: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    created_at: dt.datetime = field(default_factory=dt.datetime.now)

    def as_text(self) -> str:
        timestamp = self.created_at.strftime("%H:%M:%S")
        extras = f" | {self.context}" if self.context else ""
        return f"[{timestamp}] [{self.level.upper()}] {self.message}{extras}"


@dataclass(frozen=True)
class JobResult:
    summary: str
    detail: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobSnapshot:
    job_id: str
    name: str
    source: str
    status: str = "pending"
    progress: float = 0.0
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    cancellable: bool = True
    latest_message: str = ""
    logs: list[JobLogEntry] = field(default_factory=list)
    result: JobResult | None = None
    error_message: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class JobEvent:
    kind: str
    job_id: str
    payload: Any = None


class JobContext:
    def __init__(self, job_id: str, events: "queue.Queue[JobEvent]", cancel_event: threading.Event) -> None:
        self.job_id = job_id
        self._events = events
        self._cancel_event = cancel_event

    def emit(self, kind: str, payload: Any = None) -> None:
        self._events.put(JobEvent(kind=kind, job_id=self.job_id, payload=payload))

    def log(self, level: str, message: str, **context: Any) -> None:
        self.emit("log", JobLogEntry(level=level, message=message, context=context))

    def set_progress(self, progress: float, message: str | None = None) -> None:
        payload = {"progress": max(0.0, min(1.0, float(progress))), "message": message}
        self.emit("progress", payload)

    def set_result(self, result: JobResult) -> None:
        self.emit("result", result)

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelledError("job cancelled")
