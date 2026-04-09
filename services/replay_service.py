"""Service-layer orchestration for replay dataset loading and derived state preparation."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from core.replay import (
    ReplayAnomalyDetector,
    ReplayDataset,
    ReplayNavigationModel,
    ReplayNavigationModelBuilder,
    ReplayStateBuilder,
    RosterContext,
    StrikeZoneRuleBook,
    WarningItem,
    build_roster_context,
)
from infrastructure.postgres_repository import ReplayRepository
from services.common import ProgressReporter, ServiceResult


@dataclass(frozen=True)
class ReplayLoadRequest:
    """Input DTO for preparing a replay session from PostgreSQL."""

    conn: psycopg.Connection
    game_id: int
    strike_zone_rules: dict[int, dict[str, float]]


@dataclass
class ReplaySession:
    """Prepared replay data the GUI can render without owning business logic."""

    dataset: ReplayDataset
    roster_context: RosterContext
    state_builder: ReplayStateBuilder
    navigation: ReplayNavigationModel
    warnings: list[WarningItem]


@dataclass(frozen=True)
class ReplayLoadResult(ServiceResult):
    """Service result plus the fully prepared replay session."""

    session: ReplaySession | None = None


class ReplayService:
    """Loads replay datasets and derives navigation/state artifacts."""

    def __init__(
        self,
        *,
        anomaly_detector: ReplayAnomalyDetector | None = None,
    ) -> None:
        self.anomaly_detector = anomaly_detector or ReplayAnomalyDetector()

    def load_game(self, request: ReplayLoadRequest, context: ProgressReporter | None = None) -> ReplayLoadResult:
        if context is not None:
            context.log("info", "loading replay dataset", game_id=request.game_id)
            context.set_progress(0.1, "loading replay dataset")
        repository = ReplayRepository(request.conn)
        dataset = repository.load_game(request.game_id)

        if context is not None:
            context.set_progress(0.45, "building replay state")
        roster_context = build_roster_context(dataset)
        rule_book = StrikeZoneRuleBook(rules=dict(request.strike_zone_rules or {}))
        state_builder = ReplayStateBuilder(dataset, roster_context, rule_book)

        if context is not None:
            context.set_progress(0.75, "building replay navigation")
        navigation = ReplayNavigationModelBuilder(state_builder).build()
        warnings = self.anomaly_detector.detect(dataset.events)

        if context is not None:
            context.set_progress(1.0, "replay session ready")
        session = ReplaySession(
            dataset=dataset,
            roster_context=roster_context,
            state_builder=state_builder,
            navigation=navigation,
            warnings=warnings,
        )
        return ReplayLoadResult(
            summary="replay load completed",
            detail=f"events={len(dataset.events)} pitches={len(dataset.pitches)} warnings={len(warnings)}",
            metrics={
                "event_count": len(dataset.events),
                "pitch_count": len(dataset.pitches),
                "warning_count": len(warnings),
            },
            session=session,
        )
