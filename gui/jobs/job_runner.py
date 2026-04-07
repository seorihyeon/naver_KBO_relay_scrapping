from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import queue
import threading
import traceback
import uuid
from typing import Any, Callable

from .task_state import JobCancelledError, JobContext, JobEvent, JobResult, JobSnapshot


JobListener = Callable[[JobEvent, JobSnapshot], None]
JobWorker = Callable[[JobContext], JobResult | None]


@dataclass(frozen=True)
class JobHandle:
    job_id: str


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
            snapshot.latest_message = "Cancelled"
            return
        if event.kind == "failed":
            snapshot.status = "failed"
            snapshot.finished_at = dt.datetime.now()
            snapshot.error_message = event.payload["message"]
            snapshot.latest_message = event.payload["message"]
            return

