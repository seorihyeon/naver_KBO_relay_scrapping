from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt


Half = str


@dataclass(frozen=True)
class PlayerInfo:
    player_id: str
    player_name: str
    height_cm: int | None
    bats_throws_text: str | None
    hit_type_text: str | None
    batting_side: str | None


@dataclass(frozen=True)
class GameContext:
    game_id: int
    game_date: dt.date | None
    home_team_id: int | None
    away_team_id: int | None
    home_team_name: str
    away_team_name: str


@dataclass(frozen=True)
class EventRow:
    event_id: int
    event_seq_game: int | None
    inning_no: int | None
    half: Half | None
    pa_id: int | None
    event_seq_in_pa: int | None
    event_category: str | None
    text: str | None
    outs: int | None
    balls: int | None
    strikes: int | None
    base1_occupied: bool | None
    base2_occupied: bool | None
    base3_occupied: bool | None
    home_score: int | None
    away_score: int | None
    base1_runner_name: str | None
    base2_runner_name: str | None
    base3_runner_name: str | None
    base1_runner_id: str | None
    base2_runner_id: str | None
    base3_runner_id: str | None


@dataclass(frozen=True)
class PitchRow:
    pitch_id: int
    event_id: int | None
    pa_id: int | None
    inning_id: int | None
    pitch_num: int | None
    pitch_result: str | None
    pitch_type_text: str | None
    speed_kph: float | None
    balls_before: int | None
    strikes_before: int | None
    balls_after: int | None
    strikes_after: int | None
    is_in_play: bool | None
    is_terminal_pitch: bool | None
    cross_plate_x: float | None
    cross_plate_y: float | None
    tracking_top: float | None
    tracking_bottom: float | None
    x0: float | None
    y0: float | None
    z0: float | None
    vx0: float | None
    vy0: float | None
    vz0: float | None
    ax: float | None
    ay: float | None
    az: float | None
    stance: str | None


@dataclass(frozen=True)
class PlateAppearanceRow:
    pa_id: int
    pa_seq_game: int | None
    inning_no: int | None
    half: Half | None
    batter_id: str | None
    pitcher_id: str | None
    outs_before: int | None
    outs_after: int | None
    balls_final: int | None
    strikes_final: int | None
    result_text: str | None
    runs_scored_on_pa: int | None
    start_seqno: int | None
    end_seqno: int | None


@dataclass(frozen=True)
class InningRow:
    inning_id: int
    inning_no: int | None
    half: Half | None
    batting_team_id: int | None
    fielding_team_id: int | None
    runs_scored: int | None
    hits_in_half: int | None
    errors_in_half: int | None
    walks_in_half: int | None
    start_event_seqno: int | None
    end_event_seqno: int | None


@dataclass(frozen=True)
class RosterEntryRow:
    team_id: int | None
    player_id: str | None
    player_name: str | None
    roster_group: str | None
    is_starting_pitcher: bool | None
    field_position_code: str | None
    field_position_name: str | None


@dataclass(frozen=True)
class SubstitutionRow:
    sub_event_id: int
    event_id: int | None
    event_seq_game: int | None
    team_id: int | None
    in_player_name: str | None
    out_player_name: str | None
    in_position: str | None
    out_position: str | None
    description: str | None


@dataclass(frozen=True)
class DerivedState:
    outs: int
    balls: int
    strikes: int
    home_score: int
    away_score: int
    b1_occ: bool
    b2_occ: bool
    b3_occ: bool
    b1_name: str | None
    b2_name: str | None
    b3_name: str | None
    count_status_label: str | None = None


@dataclass(frozen=True)
class PitchContext:
    pitch: PitchRow
    plate_x: float | None
    plate_z: float | None
    zone_top: float | None
    zone_bottom: float | None
    zone_half_width: float | None
    rule_year: int
    batter_height_cm: int | None
    width_cm: float
    stance: str | None


@dataclass(frozen=True)
class EventParticipants:
    batter_name: str
    pitcher_name: str
    fielding_team_id: int | None
    fielding_team_name: str
    batting_team_id: int | None
    batting_team_name: str
    lineup: dict[str, str]
    batter_side: str | None


@dataclass(frozen=True)
class PitchNavigationItem:
    event_idx: int
    pitch: PitchRow


@dataclass(frozen=True)
class PlateAppearanceNavigationItem:
    event_idx: int
    pa: PlateAppearanceRow
    display_result_text: str


@dataclass(frozen=True)
class InningNavigationItem:
    event_idx: int
    inning: InningRow
    runs_scored: int | None


@dataclass(frozen=True)
class WarningItem:
    event_id: int
    code: str
    detail: str


@dataclass
class ReplayDataset:
    context: GameContext
    players: list[PlayerInfo]
    roster_entries: list[RosterEntryRow]
    substitutions: list[SubstitutionRow]
    events: list[EventRow]
    pitches: list[PitchRow]
    plate_appearances: list[PlateAppearanceRow]
    innings: list[InningRow]


@dataclass
class RosterContext:
    player_name_by_id: dict[str, str] = field(default_factory=dict)
    player_height_by_id: dict[str, int] = field(default_factory=dict)
    player_batting_side_by_id: dict[str, str] = field(default_factory=dict)
    player_team_by_name: dict[str, int] = field(default_factory=dict)
    team_name_by_id: dict[int | None, str] = field(default_factory=dict)
    starting_defense_by_team: dict[int, dict[str, str]] = field(default_factory=dict)
    defense_snapshots_by_event: dict[int, dict[int, dict[str, str]]] = field(default_factory=dict)
