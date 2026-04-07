from __future__ import annotations

from dataclasses import dataclass

from .models import EventRow, WarningItem


def _safe_int(value: int | None) -> int | None:
    return int(value) if value is not None else None


@dataclass
class ReplayAnomalyDetector:
    def detect(self, events: list[EventRow]) -> list[WarningItem]:
        warnings: list[WarningItem] = []
        prev_ball = prev_strike = prev_home = prev_away = None
        prev_pa = None
        for event in events:
            balls_i = _safe_int(event.balls)
            strikes_i = _safe_int(event.strikes)
            home_i = _safe_int(event.home_score)
            away_i = _safe_int(event.away_score)
            if home_i is None or away_i is None:
                warnings.append(WarningItem(event.event_id, "score_null", f"seq={event.event_seq_game} has NULL score"))
            if prev_pa is not None and event.pa_id != prev_pa:
                prev_ball = prev_strike = None
            if prev_ball is not None and balls_i is not None and balls_i < prev_ball:
                warnings.append(WarningItem(event.event_id, "balls_regressed", f"{prev_ball} -> {balls_i} at seq={event.event_seq_game}"))
            if prev_strike is not None and strikes_i is not None and strikes_i < prev_strike:
                warnings.append(WarningItem(event.event_id, "strikes_regressed", f"{prev_strike} -> {strikes_i} at seq={event.event_seq_game}"))
            if prev_home is not None and home_i is not None and home_i < prev_home:
                warnings.append(WarningItem(event.event_id, "home_score_regressed", f"{prev_home} -> {home_i} at seq={event.event_seq_game}"))
            if prev_away is not None and away_i is not None and away_i < prev_away:
                warnings.append(WarningItem(event.event_id, "away_score_regressed", f"{prev_away} -> {away_i} at seq={event.event_seq_game}"))
            prev_pa = event.pa_id
            prev_ball = balls_i if balls_i is not None else prev_ball
            prev_strike = strikes_i if strikes_i is not None else prev_strike
            prev_home = home_i if home_i is not None else prev_home
            prev_away = away_i if away_i is not None else prev_away
        return warnings
