"""GUI-independent DTOs and progress protocols for service-layer workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class GameOption:
    """Selectable game metadata shared between services and the GUI state."""

    game_id: int
    label: str


@dataclass(frozen=True)
class ServiceResult:
    """Standard service response payload understood by background jobs and tabs."""

    summary: str
    detail: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProgressReporter(Protocol):
    """Minimal reporting contract for long-running service workflows."""

    def log(self, level: str, message: str, **context: Any) -> None:
        ...

    def set_progress(self, progress: float, message: str | None = None) -> None:
        ...

    def is_cancelled(self) -> bool:
        ...

    def check_cancelled(self) -> None:
        ...

