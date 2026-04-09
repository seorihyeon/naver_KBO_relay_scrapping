from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .models import (
    DerivedState,
    EventParticipants,
    EventRow,
    PitchContext,
    PitchRow,
    PlateAppearanceRow,
    ReplayDataset,
    RosterContext,
)
from .roster import get_lineup_snapshot
from .strike_zone import StrikeZoneRuleBook


BATTER_INTRO_PATTERN = re.compile(r"^\d+번타자\s+")
ADVANCE_PATTERN = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*(?P<dst>[123])루(?:까지)?\s*진루")
HOME_PATTERN = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*홈인")
OUT_PATTERN = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*아웃")


@dataclass
class ReplayStateBuilder:
    dataset: ReplayDataset
    roster_context: RosterContext
    strike_zone_rule_book: StrikeZoneRuleBook

    def __post_init__(self) -> None:
        self.events = self.dataset.events
        self.pitches = self.dataset.pitches
        self.plate_appearances = self.dataset.plate_appearances
        self.innings = self.dataset.innings
        self.pitch_state_by_event = {
            pitch.event_id: {"balls": pitch.balls_after, "strikes": pitch.strikes_after}
            for pitch in self.pitches
            if pitch.event_id is not None
        }
        self.pa_state_by_id = {
            pa.pa_id: {
                "outs_before": pa.outs_before,
                "outs_after": pa.outs_after,
                "start_seqno": pa.start_seqno,
                "end_seqno": pa.end_seqno,
            }
            for pa in self.plate_appearances
        }
        self.pa_lookup_by_id = {
            pa.pa_id: {
                "pa_id": pa.pa_id,
                "pa_seq_game": pa.pa_seq_game,
                "inning_no": pa.inning_no,
                "half": pa.half,
                "batter_id": pa.batter_id,
                "pitcher_id": pa.pitcher_id,
                "result_text": pa.result_text or "-",
            }
            for pa in self.plate_appearances
        }
        self.derived_state_by_event = self.build_derived_state_map()

    def get_player_name(self, player_id: str | None, fallback: str = "-") -> str:
        if player_id and player_id in self.roster_context.player_name_by_id:
            return self.roster_context.player_name_by_id[player_id]
        return fallback

    def get_team_name(self, team_id: int | None, fallback: str = "-") -> str:
        if team_id in self.roster_context.team_name_by_id:
            return self.roster_context.team_name_by_id[team_id]
        return fallback

    def infer_batter_name_from_text(self, text: str | None) -> str | None:
        if not text:
            return None
        match = re.match(r"([^ :]+)\s*:", text.strip())
        if match:
            return match.group(1).strip()
        return None

    def format_inning_label(self, inning_no: int | None, half: str | None) -> str:
        if inning_no is None:
            return "이닝 미상"
        return f"{inning_no}{'초' if half == 'top' else '말'}"

    def cm_to_ft(self, cm_value: float | None) -> float | None:
        if cm_value is None:
            return None
        return float(cm_value) / 30.48

    def get_game_year(self) -> int | None:
        return getattr(self.dataset.context.game_date, "year", None)

    def get_regulation_strike_zone(
        self,
        batter_id: str | None,
        *,
        fallback_top: float | None = None,
        fallback_bottom: float | None = None,
    ) -> dict[str, float | int | None]:
        height_cm = self.roster_context.player_height_by_id.get(batter_id or "")
        rule = self.strike_zone_rule_book.get_rule(self.get_game_year())
        if height_cm:
            top_ft = self.cm_to_ft(height_cm * float(rule["top_pct"]))
            bottom_ft = self.cm_to_ft(height_cm * float(rule["bottom_pct"]))
        else:
            top_ft = fallback_top
            bottom_ft = fallback_bottom
        half_width_ft = self.cm_to_ft(float(rule["width_cm"]) / 2.0)
        return {
            "top_ft": top_ft,
            "bottom_ft": bottom_ft,
            "half_width_ft": half_width_ft,
            "height_cm": height_cm,
            "effective_year": int(rule["effective_year"]),
            "width_cm": float(rule["width_cm"]),
        }

    def solve_pitch_plate_height(self, pitch: PitchRow) -> float | None:
        values = [
            pitch.cross_plate_y,
            pitch.y0,
            pitch.vy0,
            pitch.ay,
            pitch.z0,
            pitch.vz0,
            pitch.az,
        ]
        if any(value is None for value in values):
            return None
        a = 0.5 * float(pitch.ay)
        b = float(pitch.vy0)
        c = float(pitch.y0) - float(pitch.cross_plate_y)
        if abs(a) < 1e-9:
            if abs(b) < 1e-9:
                return None
            t = -c / b
        else:
            discriminant = b * b - 4 * a * c
            if discriminant < 0:
                return None
            root = math.sqrt(discriminant)
            candidates = [(-b - root) / (2 * a), (-b + root) / (2 * a)]
            positive_times = [candidate for candidate in candidates if candidate >= 0]
            if not positive_times:
                return None
            t = min(positive_times)
        if t < 0:
            return None
        return float(pitch.z0) + float(pitch.vz0) * t + 0.5 * float(pitch.az) * t * t

    def current_pitch_tracking(self, pitch: PitchRow | None) -> PitchContext | None:
        if pitch is None:
            return None
        pa_info = self.pa_lookup_by_id.get(pitch.pa_id or -1, {})
        regulation_zone = self.get_regulation_strike_zone(
            pa_info.get("batter_id"),
            fallback_top=pitch.tracking_top,
            fallback_bottom=pitch.tracking_bottom,
        )
        plate_z = self.solve_pitch_plate_height(pitch)
        return PitchContext(
            pitch=pitch,
            plate_x=pitch.cross_plate_x,
            plate_z=plate_z,
            zone_top=regulation_zone["top_ft"],
            zone_bottom=regulation_zone["bottom_ft"],
            zone_half_width=regulation_zone["half_width_ft"],
            rule_year=int(regulation_zone["effective_year"] or self.get_game_year() or 0),
            batter_height_cm=regulation_zone["height_cm"],
            width_cm=float(regulation_zone["width_cm"] or 0.0),
            stance=pitch.stance,
        )

    def resolve_batter_stance(
        self,
        batter_id: str | None,
        *,
        event: EventRow | None = None,
        pitch: PitchRow | None = None,
    ) -> str | None:
        pitch_context = self.current_pitch_tracking(pitch)
        if pitch_context and event and pitch_context.pitch.pa_id == event.pa_id and pitch_context.stance in {"L", "R", "S"}:
            return pitch_context.stance
        if batter_id:
            return self.roster_context.player_batting_side_by_id.get(batter_id)
        return None

    def get_fielding_team_id(self, event: EventRow) -> int | None:
        if event.half == "top":
            return self.dataset.context.home_team_id
        if event.half == "bottom":
            return self.dataset.context.away_team_id
        return None

    def get_batting_team_id(self, event: EventRow) -> int | None:
        if event.half == "top":
            return self.dataset.context.away_team_id
        if event.half == "bottom":
            return self.dataset.context.home_team_id
        return None

    def get_event_participants(self, event: EventRow, *, pitch: PitchRow | None = None) -> EventParticipants:
        pa_info = self.pa_lookup_by_id.get(event.pa_id or -1, {})
        batter_id = pa_info.get("batter_id")
        batter_name = self.get_player_name(batter_id) if batter_id else "-"
        pitcher_name = self.get_player_name(pa_info.get("pitcher_id")) if pa_info.get("pitcher_id") else "-"
        if batter_name == "-":
            batter_name = self.infer_batter_name_from_text(event.text) or "-"
        fielding_team_id = self.get_fielding_team_id(event)
        batting_team_id = self.get_batting_team_id(event)
        lineup = get_lineup_snapshot(event.event_id, fielding_team_id, self.roster_context)
        if pitcher_name == "-" and lineup.get("P"):
            pitcher_name = lineup["P"]
        return EventParticipants(
            batter_name=batter_name,
            pitcher_name=pitcher_name,
            fielding_team_id=fielding_team_id,
            fielding_team_name=self.get_team_name(fielding_team_id, "수비"),
            batting_team_id=batting_team_id,
            batting_team_name=self.get_team_name(batting_team_id, "공격"),
            lineup=lineup,
            batter_side=self.resolve_batter_stance(batter_id, event=event, pitch=pitch),
        )

    def is_meaningful_pa_text(self, text: str | None) -> bool:
        clean_text = (text or "").strip()
        if not clean_text or clean_text == "-":
            return False
        if BATTER_INTRO_PATTERN.match(clean_text):
            return False
        return True

    def get_pa_display_text(self, pa: PlateAppearanceRow, *, anchor_event_idx: int, event_indices_by_pa_id: dict[int, list[int]]) -> str:
        raw_result = (pa.result_text or "").strip()
        if self.is_meaningful_pa_text(raw_result):
            return raw_result

        anchor_text = None
        pa_state = self.pa_state_by_id.get(pa.pa_id, {})
        seq_candidates = [pa_state.get("end_seqno"), pa_state.get("start_seqno")]
        event_index_by_seq = {event.event_seq_game: idx for idx, event in enumerate(self.events) if event.event_seq_game is not None}
        for seqno in seq_candidates:
            if seqno is None:
                continue
            anchor_idx = event_index_by_seq.get(seqno)
            if anchor_idx is None or anchor_idx > anchor_event_idx:
                continue
            candidate = (self.events[anchor_idx].text or "").strip()
            if self.is_meaningful_pa_text(candidate):
                anchor_text = candidate
                break

        current_event = self.events[anchor_event_idx] if 0 <= anchor_event_idx < len(self.events) else None
        if current_event and current_event.pa_id == pa.pa_id and current_event.event_category == "baserunning" and anchor_text:
            return anchor_text

        for candidate_idx in reversed(event_indices_by_pa_id.get(pa.pa_id, [])):
            if candidate_idx > anchor_event_idx:
                continue
            candidate = (self.events[candidate_idx].text or "").strip()
            if self.is_meaningful_pa_text(candidate):
                return candidate
        return anchor_text or "타석 진행 중"

    def normalize_runner_name(self, name: str | None) -> str | None:
        text = str(name or "").strip()
        if text in {"", "-", "주자", "-주자"}:
            return None
        text = re.sub(r"^[123]루주자\s*", "", text).strip()
        if text in {"", "-", "주자"}:
            return None
        return text

    def resolve_runner_name(self, event: EventRow, base_no: int, fallback_name: str | None = None) -> str | None:
        clean_name = self.normalize_runner_name(fallback_name)
        if clean_name:
            return clean_name
        explicit_name = self.normalize_runner_name(
            {
                1: event.base1_runner_name,
                2: event.base2_runner_name,
                3: event.base3_runner_name,
            }.get(base_no)
        )
        if explicit_name:
            return explicit_name
        runner_id = {
            1: event.base1_runner_id,
            2: event.base2_runner_id,
            3: event.base3_runner_id,
        }.get(base_no)
        if not runner_id:
            return None
        return self.normalize_runner_name(self.roster_context.player_name_by_id.get(runner_id))

    def find_runner_base(self, runner_names: dict[int, str | None], runner_name: str) -> int | None:
        for base_no in (1, 2, 3):
            if runner_names.get(base_no) == runner_name:
                return base_no
        return None

    def get_event_runner_hint(self, event: EventRow, base_no: int) -> str | None:
        explicit_name = self.normalize_runner_name(
            {
                1: event.base1_runner_name,
                2: event.base2_runner_name,
                3: event.base3_runner_name,
            }.get(base_no)
        )
        runner_id = {
            1: event.base1_runner_id,
            2: event.base2_runner_id,
            3: event.base3_runner_id,
        }.get(base_no)
        id_name = self.normalize_runner_name(self.roster_context.player_name_by_id.get(runner_id)) if runner_id else None
        if explicit_name and id_name and explicit_name != id_name:
            return explicit_name
        return explicit_name or id_name

    def infer_batter_target_base(self, text: str | None) -> int | None:
        if not text:
            return None
        if "홈런" in text:
            return 4
        if "3루타" in text:
            return 3
        if "2루타" in text:
            return 2
        if any(
            keyword in text
            for keyword in [
                "1루타",
                "볼넷",
                "고의4구",
                "자동 고의4구",
                "몸에 맞는 볼",
                "낫아웃으로 출루",
                "출루",
            ]
        ):
            return 1
        return None

    def parse_runner_movements(self, text: str | None) -> list[dict[str, int | str]]:
        if not text:
            return []
        moves: list[dict[str, int | str]] = []
        for match in ADVANCE_PATTERN.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": int(match.group("dst"))})
        for match in HOME_PATTERN.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": "home"})
        for match in OUT_PATTERN.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": "out"})
        return moves

    def apply_runner_movements(self, runner_names: dict[int, str | None], text: str | None) -> None:
        for move in self.parse_runner_movements(text):
            runner_name = self.normalize_runner_name(str(move["name"]))
            if not runner_name:
                continue
            current_base = self.find_runner_base(runner_names, runner_name)
            destination = move["dst"]
            if destination in {1, 2, 3}:
                if current_base is not None and current_base != destination:
                    runner_names[current_base] = None
                runner_names[int(destination)] = runner_name
            elif current_base is not None:
                runner_names[current_base] = None

    def assign_remaining_runners(
        self,
        previous_names: dict[int, str | None],
        runner_names: dict[int, str | None],
        occupied: dict[int, bool],
    ) -> None:
        assigned = {name for name in runner_names.values() if name}
        remaining_previous: list[tuple[int, str]] = []
        for prev_base in (3, 2, 1):
            runner_name = previous_names.get(prev_base)
            if runner_name and runner_name not in assigned:
                remaining_previous.append((prev_base, runner_name))

        for base_no in (1, 2, 3):
            if not occupied[base_no] or runner_names.get(base_no):
                continue
            same_base_name = previous_names.get(base_no)
            if same_base_name and same_base_name not in assigned:
                runner_names[base_no] = same_base_name
                assigned.add(same_base_name)

        available_bases = [base_no for base_no in (3, 2, 1) if occupied[base_no] and not runner_names.get(base_no)]
        for prev_base, runner_name in remaining_previous:
            if runner_name in assigned:
                continue
            higher_or_same = [base_no for base_no in available_bases if base_no >= prev_base]
            target_base = higher_or_same[0] if higher_or_same else (available_bases[0] if available_bases else None)
            if target_base is None:
                continue
            runner_names[target_base] = runner_name
            assigned.add(runner_name)
            available_bases.remove(target_base)

    def reconcile_runner_names(self, previous_names: dict[int, str | None], event: EventRow) -> dict[int, str | None]:
        text = (event.text or "").strip()
        occupied = {
            1: bool(event.base1_occupied) if event.base1_occupied is not None else False,
            2: bool(event.base2_occupied) if event.base2_occupied is not None else False,
            3: bool(event.base3_occupied) if event.base3_occupied is not None else False,
        }
        runner_names = previous_names.copy()
        for base_no in (1, 2, 3):
            if not occupied[base_no]:
                runner_names[base_no] = None

        self.apply_runner_movements(runner_names, text)
        pa_info = self.pa_lookup_by_id.get(event.pa_id or -1, {})
        batter_name = (
            self.get_player_name(pa_info.get("batter_id"))
            if pa_info.get("batter_id")
            else self.infer_batter_name_from_text(text)
        )
        batter_target = self.infer_batter_target_base(text)
        if batter_name and batter_target in {1, 2, 3}:
            runner_names[batter_target] = batter_name

        for base_no in (1, 2, 3):
            explicit_name = self.get_event_runner_hint(event, base_no)
            if occupied[base_no] and explicit_name:
                runner_names[base_no] = explicit_name

        self.assign_remaining_runners(previous_names, runner_names, occupied)

        for base_no in (1, 2, 3):
            if not occupied[base_no]:
                runner_names[base_no] = None
        return runner_names

    def build_derived_state_map(self) -> dict[int, dict[str, int | bool | str | None]]:
        derived: dict[int, dict[str, int | bool | str | None]] = {}
        balls = strikes = outs = 0
        runner_names = {1: None, 2: None, 3: None}
        for event in self.events:
            text = (event.text or "").strip()
            occupied = {
                1: bool(event.base1_occupied) if event.base1_occupied is not None else False,
                2: bool(event.base2_occupied) if event.base2_occupied is not None else False,
                3: bool(event.base3_occupied) if event.base3_occupied is not None else False,
            }
            if "번타자" in text:
                balls, strikes = 0, 0
            if re.search(r"\d+구\s*볼", text) and "볼넷" not in text and "몸에 맞는 볼" not in text:
                balls = min(4, balls + 1)
            if "스트라이크" in text and "자동 고의4구" not in text:
                strikes = min(3, strikes + 1)
            if "헛스윙" in text and strikes < 2:
                strikes += 1
            if "파울" in text and strikes < 2:
                strikes += 1
            if any(keyword in text for keyword in ["볼넷", "고의4구", "몸에 맞는 볼"]):
                balls, strikes = 0, 0
            if "아웃" in text:
                outs = min(3, outs + 1)
                balls, strikes = 0, 0
            if "공수교대" in text or "이닝 종료" in text:
                outs, balls, strikes = 0, 0, 0
                runner_names = {1: None, 2: None, 3: None}

            runner_names = self.reconcile_runner_names(runner_names, event)
            derived[event.event_id] = {
                "outs": outs,
                "balls": balls,
                "strikes": strikes,
                "b1_occ": occupied[1],
                "b2_occ": occupied[2],
                "b3_occ": occupied[3],
                "b1_name": runner_names[1],
                "b2_name": runner_names[2],
                "b3_name": runner_names[3],
            }
        return derived

    def get_count_status_label(self, event: EventRow) -> str | None:
        text = (event.text or "").strip()
        if "삼진" in text:
            return "K"
        if "몸에 맞는 볼" in text:
            return "HBP"
        if any(keyword in text for keyword in ["볼넷", "고의4구", "자동 고의4구"]):
            return "BB"
        return None

    def get_resolved_game_state(self, event_idx: int) -> DerivedState:
        event = self.events[event_idx]
        derived = self.derived_state_by_event.get(event.event_id, {})
        balls = event.balls if event.balls is not None else int(derived.get("balls", 0) or 0)
        strikes = event.strikes if event.strikes is not None else int(derived.get("strikes", 0) or 0)
        outs = event.outs if event.outs is not None else int(derived.get("outs", 0) or 0)
        state = DerivedState(
            outs=outs,
            balls=balls,
            strikes=strikes,
            home_score=event.home_score or 0,
            away_score=event.away_score or 0,
            b1_occ=bool(event.base1_occupied) if event.base1_occupied is not None else bool(derived.get("b1_occ", False)),
            b2_occ=bool(event.base2_occupied) if event.base2_occupied is not None else bool(derived.get("b2_occ", False)),
            b3_occ=bool(event.base3_occupied) if event.base3_occupied is not None else bool(derived.get("b3_occ", False)),
            b1_name=self.resolve_runner_name(event, 1, derived.get("b1_name")),
            b2_name=self.resolve_runner_name(event, 2, derived.get("b2_name")),
            b3_name=self.resolve_runner_name(event, 3, derived.get("b3_name")),
            count_status_label=self.get_count_status_label(event),
        )
        return state
