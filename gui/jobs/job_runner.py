from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import queue
import threading
import traceback
import uuid
from typing import Any, Callable

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
    result: Any | None = None
    error_message: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class JobEvent:
    kind: str
    job_id: str
    payload: Any = None


@dataclass(frozen=True)
class JobHandle:
    job_id: str


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

    def set_result(self, result: Any) -> None:
        self.emit("result", result)

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelledError("작업이 취소되었습니다")


JobListener = Callable[[JobEvent, JobSnapshot], None]
JobWorker = Callable[[JobContext], Any | None]


class JobRunner:
    def __init__(self) -> None:
        self._jobs: dict[str, JobSnapshot] = {}
        self._job_queues: dict[str, "queue.Queue[JobEvent]"] = {}
        self._job_cancellations: dict[str, threading.Event] = {}
        self._listeners: dict[str, JobListener | None] = {}

    def start_job(self, *, name: str, source: str, worker: JobWorker, listener: JobListener | None = None) -> JobHandle:
        job_id = uuid.uuid4().hex
        snapshot = JobSnapshot(job_id=job_id, name=name, source=source, status="running", started_at=dt.datetime.now())
        event_queue: "queue.Queue[JobEvent]" = queue.Queue()
        cancel_event = threading.Event()
        self._jobs[job_id] = snapshot
        self._job_queues[job_id] = event_queue
        self._job_cancellations[job_id] = cancel_event
        self._listeners[job_id] = listener

        def runner() -> None:
            ctx = JobContext(job_id=job_id, events=event_queue, cancel_event=cancel_event)
            try:
                result = worker(ctx)
                if cancel_event.is_set():
                    event_queue.put(JobEvent(kind="cancelled", job_id=job_id))
                    return
                if result is not None:
                    event_queue.put(JobEvent(kind="result", job_id=job_id, payload=result))
                event_queue.put(JobEvent(kind="completed", job_id=job_id))
            except JobCancelledError:
                event_queue.put(JobEvent(kind="cancelled", job_id=job_id))
            except Exception as exc:
                payload = {"message": str(exc), "traceback": traceback.format_exc()}
                event_queue.put(JobEvent(kind="failed", job_id=job_id, payload=payload))

        threading.Thread(target=runner, daemon=True).start()
        return JobHandle(job_id=job_id)

    def cancel(self, job_id: str) -> None:
        cancel_event = self._job_cancellations.get(job_id)
        if cancel_event:
            cancel_event.set()

    def get_snapshot(self, job_id: str) -> JobSnapshot | None:
        return self._jobs.get(job_id)

    def poll(self) -> None:
        for job_id, event_queue in list(self._job_queues.items()):
            snapshot = self._jobs[job_id]
            listener = self._listeners.get(job_id)
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break
                self._apply_event(snapshot, event)
                if listener is not None:
                    listener(event, snapshot)

    def _apply_event(self, snapshot: JobSnapshot, event: JobEvent) -> None:
        if event.kind == "log":
            snapshot.logs.append(event.payload)
            snapshot.latest_message = event.payload.message
            return
        if event.kind == "progress":
            snapshot.progress = float(event.payload.get("progress", snapshot.progress))
            snapshot.latest_message = event.payload.get("message") or snapshot.latest_message
            return
        if event.kind == "result":
            snapshot.result = event.payload
            if event.payload.detail:
                snapshot.latest_message = event.payload.detail
            else:
                snapshot.latest_message = event.payload.summary
            return
        if event.kind == "completed":
            snapshot.status = "completed"
            snapshot.progress = 1.0
            snapshot.finished_at = dt.datetime.now()
            return
        if event.kind == "cancelled":
            snapshot.status = "cancelled"
            snapshot.finished_at = dt.datetime.now()
            snapshot.latest_message = "취소됨"
            return
        if event.kind == "failed":
            snapshot.status = "failed"
            snapshot.finished_at = dt.datetime.now()
            snapshot.error_message = event.payload["message"]
            snapshot.latest_message = event.payload["message"]
            return
