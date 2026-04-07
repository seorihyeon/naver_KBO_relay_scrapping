from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gui.jobs import JobRunner
from gui.state import AppState


@dataclass(frozen=True)
class RegisteredTab:
    key: str
    factory: Callable[[AppState, JobRunner, Callable[[], None]], object]


def build_default_tabs(state: AppState, job_runner: JobRunner, request_layout: Callable[[], None]) -> list[object]:
    from tabs.collection_tab import CollectionTab
    from tabs.editor_tab import CorrectionEditorTab
    from tabs.ingestion_tab import IngestionTab
    from tabs.replay_tab import ReplayTab

    definitions = [
        RegisteredTab("collection", lambda app_state, runner, layout: CollectionTab(app_state, runner, layout)),
        RegisteredTab("editor", lambda app_state, runner, layout: CorrectionEditorTab(app_state)),
        RegisteredTab("ingestion", lambda app_state, runner, layout: IngestionTab(app_state, runner, layout)),
        RegisteredTab("replay", lambda app_state, runner, layout: ReplayTab(app_state, runner, layout)),
    ]
    return [definition.factory(state, job_runner, request_layout) for definition in definitions]
