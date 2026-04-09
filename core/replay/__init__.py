"""Pure replay-domain models and state derivation logic."""

from .anomaly import ReplayAnomalyDetector
from .models import (
    DerivedState,
    EventParticipants,
    EventRow,
    GameContext,
    InningNavigationItem,
    InningRow,
    PitchContext,
    PitchNavigationItem,
    PitchRow,
    PlateAppearanceNavigationItem,
    PlateAppearanceRow,
    ReplayDataset,
    RosterContext,
    WarningItem,
)
from .navigation import ReplayNavigationModel, ReplayNavigationModelBuilder, find_last_nav_index_at_or_before
from .roster import build_roster_context, get_lineup_snapshot
from .state_builder import ReplayStateBuilder
from .strike_zone import DEFAULT_STRIKE_ZONE_RULES, StrikeZoneRuleBook

__all__ = [
    "DEFAULT_STRIKE_ZONE_RULES",
    "DerivedState",
    "EventParticipants",
    "EventRow",
    "GameContext",
    "InningNavigationItem",
    "InningRow",
    "PitchContext",
    "PitchNavigationItem",
    "PitchRow",
    "PlateAppearanceNavigationItem",
    "PlateAppearanceRow",
    "ReplayAnomalyDetector",
    "ReplayDataset",
    "ReplayNavigationModel",
    "ReplayNavigationModelBuilder",
    "ReplayStateBuilder",
    "RosterContext",
    "StrikeZoneRuleBook",
    "WarningItem",
    "build_roster_context",
    "find_last_nav_index_at_or_before",
    "get_lineup_snapshot",
]
