from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    EventRow,
    InningNavigationItem,
    InningRow,
    PitchNavigationItem,
    PitchRow,
    PlateAppearanceNavigationItem,
    PlateAppearanceRow,
)
from .state_builder import ReplayStateBuilder


@dataclass
class ReplayNavigationModel:
    event_index_by_id: dict[int, int] = field(default_factory=dict)
    event_index_by_seq: dict[int, int] = field(default_factory=dict)
    event_indices_by_pa_id: dict[int, list[int]] = field(default_factory=dict)
    event_indices_by_inning_key: dict[tuple[int | None, str | None], list[int]] = field(default_factory=dict)
    pitch_items: list[PitchNavigationItem] = field(default_factory=list)
    pa_items: list[PlateAppearanceNavigationItem] = field(default_factory=list)
    inning_items: list[InningNavigationItem] = field(default_factory=list)
    pa_index_by_id: dict[int, int] = field(default_factory=dict)
    inning_index_by_key: dict[tuple[int | None, str | None], int] = field(default_factory=dict)


@dataclass
class ReplayNavigationModelBuilder:
    state_builder: ReplayStateBuilder

    def build(self) -> ReplayNavigationModel:
        model = ReplayNavigationModel()
        events = self.state_builder.events
        pitches = self.state_builder.pitches
        plate_appearances = self.state_builder.plate_appearances
        innings = self.state_builder.innings

        model.event_index_by_id = {event.event_id: idx for idx, event in enumerate(events)}
        model.event_index_by_seq = {
            event.event_seq_game: idx
            for idx, event in enumerate(events)
            if event.event_seq_game is not None
        }

        for idx, event in enumerate(events):
            if event.pa_id is not None:
                model.event_indices_by_pa_id.setdefault(event.pa_id, []).append(idx)
            inning_key = (event.inning_no, event.half)
            model.event_indices_by_inning_key.setdefault(inning_key, []).append(idx)

        model.pitch_items = self._build_pitch_items(pitches, model.event_index_by_id)
        model.pa_items, model.pa_index_by_id = self._build_pa_items(plate_appearances, model)
        model.inning_items, model.inning_index_by_key = self._build_inning_items(innings, model)
        return model

    def _build_pitch_items(self, pitches: list[PitchRow], event_index_by_id: dict[int, int]) -> list[PitchNavigationItem]:
        items: list[PitchNavigationItem] = []
        for pitch in pitches:
            if pitch.event_id is None:
                continue
            event_idx = event_index_by_id.get(pitch.event_id)
            if event_idx is None:
                continue
            items.append(PitchNavigationItem(event_idx=event_idx, pitch=pitch))
        items.sort(key=lambda item: (item.event_idx, item.pitch.pitch_id))
        return items

    def _build_pa_items(
        self,
        plate_appearances: list[PlateAppearanceRow],
        model: ReplayNavigationModel,
    ) -> tuple[list[PlateAppearanceNavigationItem], dict[int, int]]:
        items: list[PlateAppearanceNavigationItem] = []
        pa_index_by_id: dict[int, int] = {}
        last_item: PlateAppearanceNavigationItem | None = None
        for pa in plate_appearances:
            fallback_indices = model.event_indices_by_pa_id.get(pa.pa_id, [])
            event_idx = fallback_indices[-1] if fallback_indices else self.resolve_anchor_event_index(
                model.event_index_by_seq,
                start_seqno=pa.start_seqno,
                end_seqno=pa.end_seqno,
                fallback_indices=fallback_indices,
                prefer_last=True,
            )
            if event_idx is None:
                continue
            if last_item and self.should_merge_pa_with_previous(pa, last_item.pa):
                pa_index_by_id[pa.pa_id] = len(items) - 1
                continue
            display_text = self.state_builder.get_pa_display_text(
                pa,
                anchor_event_idx=event_idx,
                event_indices_by_pa_id=model.event_indices_by_pa_id,
            )
            item = PlateAppearanceNavigationItem(event_idx=event_idx, pa=pa, display_result_text=display_text)
            pa_index_by_id[pa.pa_id] = len(items)
            items.append(item)
            last_item = item
        return items, pa_index_by_id

    def _build_inning_items(
        self,
        innings: list[InningRow],
        model: ReplayNavigationModel,
    ) -> tuple[list[InningNavigationItem], dict[tuple[int | None, str | None], int]]:
        items: list[InningNavigationItem] = []
        inning_index_by_key: dict[tuple[int | None, str | None], int] = {}
        for inning in innings:
            inning_key = (inning.inning_no, inning.half)
            fallback_indices = model.event_indices_by_inning_key.get(inning_key, [])
            event_idx = fallback_indices[0] if fallback_indices else self.resolve_anchor_event_index(
                model.event_index_by_seq,
                start_seqno=inning.start_event_seqno,
                end_seqno=inning.end_event_seqno,
                fallback_indices=fallback_indices,
                prefer_last=False,
            )
            if event_idx is None:
                continue
            inning_index_by_key[inning_key] = len(items)
            items.append(
                InningNavigationItem(
                    event_idx=event_idx,
                    inning=inning,
                    runs_scored=self.compute_inning_runs(inning, fallback_indices),
                )
            )
        return items, inning_index_by_key

    def should_merge_pa_with_previous(self, current: PlateAppearanceRow, previous: PlateAppearanceRow) -> bool:
        if self.state_builder.is_meaningful_pa_text(current.result_text):
            return False
        if current.batter_id != previous.batter_id or current.pitcher_id != previous.pitcher_id:
            return False
        if previous.end_seqno is not None and current.start_seqno is not None and current.start_seqno > previous.end_seqno + 1:
            return False
        event_indices = self._event_indices_for_pa(current.pa_id)
        if not event_indices:
            return False
        categories = {self.state_builder.events[idx].event_category or "" for idx in event_indices}
        return bool(categories) and categories.issubset({"baserunning", "other"})

    def _event_indices_for_pa(self, pa_id: int) -> list[int]:
        indices: list[int] = []
        for idx, event in enumerate(self.state_builder.events):
            if event.pa_id == pa_id:
                indices.append(idx)
        return indices

    def compute_inning_runs(self, inning: InningRow, event_indices: list[int], fallback_runs: int | None = None) -> int | None:
        if not event_indices:
            return fallback_runs or 0
        start_idx = min(event_indices)
        end_idx = max(event_indices)
        prev_home = prev_away = 0
        if start_idx > 0:
            prev_state = self.state_builder.get_resolved_game_state(start_idx - 1)
            prev_home = prev_state.home_score
            prev_away = prev_state.away_score
        end_state = self.state_builder.get_resolved_game_state(end_idx)
        computed_runs = end_state.away_score - prev_away if inning.half == "top" else end_state.home_score - prev_home
        if computed_runs < 0:
            return fallback_runs or 0
        if fallback_runs is not None and computed_runs == 0 and fallback_runs > 0:
            return fallback_runs
        return computed_runs

    def resolve_anchor_event_index(
        self,
        event_index_by_seq: dict[int, int],
        *,
        start_seqno: int | None,
        end_seqno: int | None,
        fallback_indices: list[int],
        prefer_last: bool,
    ) -> int | None:
        for seqno in (end_seqno, start_seqno):
            if seqno is None:
                continue
            event_idx = event_index_by_seq.get(seqno)
            if event_idx is not None:
                return event_idx
        if fallback_indices:
            return fallback_indices[-1] if prefer_last else fallback_indices[0]
        return None


def find_last_nav_index_at_or_before(items: list[PitchNavigationItem | PlateAppearanceNavigationItem | InningNavigationItem], event_idx: int) -> int:
    if not items:
        return 0
    match_idx = 0
    for idx, item in enumerate(items):
        if item.event_idx <= event_idx:
            match_idx = idx
        else:
            break
    return match_idx
