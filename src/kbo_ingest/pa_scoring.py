from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping

from .common_utils import to_int


BATTER_STAT_KEYS = (
    "pa",
    "ab",
    "hit",
    "bb",
    "ibb",
    "so",
    "hbp",
    "sh",
    "sf",
    "ci",
    "roe",
    "fc",
    "dp",
    "hr",
)
PITCHER_STAT_KEYS = ("bf", "pa", "ab", "hit", "bb", "ibb", "so", "hbp", "hr", "bbhp")
HITTER_ADVANTAGE_COUNTS = {(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)}
BAT_RESULT_TYPE_CODES = {13, 23}
BASERUN_KEYWORDS = ("주루", "진루", "홈인", "견제", "세이프", "아웃", "도루", "송구", "포스아웃", "실책")
BAT_RESULT_KEYWORDS = (
    "1루타",
    "2루타",
    "3루타",
    "내야안타",
    "번트안타",
    "안타",
    "홈런",
    "삼진",
    "땅볼",
    "플라이 아웃",
    "파울플라이 아웃",
    "직선타",
    "볼넷",
    "고의4구",
    "자동 고의4구",
    "몸에 맞는 볼",
    "병살",
    "희생플라이",
    "희생번트",
    "낫아웃",
    "아웃",
    "야수선택",
    "타격방해",
    "출루",
)
RUNNER_EVENT_PREFIX_RE = re.compile(r"^(?:[123]루주자|타자주자)\s+")
PICKOFF_ATTEMPT_RE = re.compile(r"^[123]루\s+견제 시도")


@dataclass(slots=True)
class ScoringEvent:
    inning_no: int
    half: str
    seqno: int
    type_code: int | None
    event_category: str
    text: str
    batter_id: str | None
    pitcher_id: str | None
    balls: int | None
    strikes: int | None
    outs: int | None
    base1: bool
    base2: bool
    base3: bool
    pitch_num: int | None
    pitch_result: str | None
    pts_pitch_id: str | None
    player_change: dict[str, Any]
    raw_payload: dict[str, Any]

    @property
    def offense_side(self) -> str:
        return "away" if self.half == "top" else "home"

    @property
    def defense_side(self) -> str:
        return "home" if self.half == "top" else "away"

    @property
    def in_key(self) -> tuple[int, str]:
        return (self.inning_no, self.half)


@dataclass(slots=True)
class SubstitutionSnapshot:
    from_player_id: str | None
    to_player_id: str | None
    balls: int | None
    strikes: int | None
    seqno: int
    text: str


@dataclass(slots=True)
class TerminalPAResult:
    category: str
    stats: dict[str, int]
    is_walk: bool = False
    is_strikeout: bool = False


@dataclass(slots=True)
class ScoredPlateAppearance:
    inning_no: int
    half: str
    offense_side: str
    defense_side: str
    start_seqno: int
    end_seqno: int
    is_terminal: bool
    result_text: str
    official_result_category: str | None
    starting_batter_id: str | None
    finishing_batter_id: str | None
    batter_credit_owner_id: str | None
    starting_pitcher_id: str | None
    finishing_pitcher_id: str | None
    pitcher_credit_owner_id: str | None
    batter_substitution_count: tuple[int | None, int | None] | None
    pitcher_substitution_count: tuple[int | None, int | None] | None
    batter_stats: dict[str, int]
    pitcher_stats: dict[str, int]


@dataclass(slots=True)
class PlateAppearanceContext:
    inning_no: int
    half: str
    offense_side: str
    defense_side: str
    start_seqno: int
    starting_batter_id: str | None
    current_batter_id: str | None
    starting_pitcher_id: str | None
    current_pitcher_id: str | None
    has_batter_action: bool = False
    end_seqno: int = 0
    pitch_events: list[ScoringEvent] = field(default_factory=list)
    batter_substitutions: list[SubstitutionSnapshot] = field(default_factory=list)
    pitcher_substitutions: list[SubstitutionSnapshot] = field(default_factory=list)

    @property
    def in_key(self) -> tuple[int, str]:
        return (self.inning_no, self.half)


@dataclass(slots=True)
class PAScoringSummary:
    terminal_plate_appearances: int
    partial_plate_appearances: int
    scored_plate_appearances: list[ScoredPlateAppearance]
    batter_totals_by_side: dict[str, dict[str, dict[str, int]]]
    batter_team_totals: dict[str, dict[str, int]]
    pitcher_totals_by_side: dict[str, dict[str, dict[str, int]]]
    pitcher_team_totals: dict[str, dict[str, int]]


def _normalize_half(home_or_away: Any) -> str | None:
    txt = str(home_or_away).strip().upper()
    if txt in {"0", "TOP", "T", "AWAY"}:
        return "top"
    if txt in {"1", "BOTTOM", "B", "HOME"}:
        return "bottom"
    return None


def _event_description(text: str) -> str:
    if ":" not in text:
        return ""
    return text.split(":", maxsplit=1)[1].strip()


def _is_baserunning_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if RUNNER_EVENT_PREFIX_RE.match(stripped) or PICKOFF_ATTEMPT_RE.match(stripped):
        return True
    desc = _event_description(stripped)
    return bool(desc) and any(keyword in desc for keyword in BASERUN_KEYWORDS)


def _is_bat_result_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if RUNNER_EVENT_PREFIX_RE.match(stripped) or PICKOFF_ATTEMPT_RE.match(stripped):
        return False
    desc = _event_description(stripped)
    if not desc:
        return False
    return any(keyword in desc for keyword in BAT_RESULT_KEYWORDS)


def _is_batter_intro_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    return bool(re.match(r"^\d+번타자\s+\S+", stripped) or re.match(r"^대타\s+\S+", stripped))


def classify_event(
    text: str,
    pitch_num: int | None,
    pitch_result: str | None,
    pts_pitch_id: str | None,
    player_change: Any,
    type_code: int | None = None,
) -> str:
    txt = text or ""
    if pitch_num is not None or pitch_result or pts_pitch_id:
        return "pitch"
    if type_code in BAT_RESULT_TYPE_CODES:
        return "bat_result"
    if player_change:
        return "substitution"
    if "비디오 판독" in txt:
        return "review"
    if "회" in txt and ("공격" in txt or "말" in txt or "초" in txt):
        return "header"
    if _is_bat_result_text(txt):
        return "bat_result"
    if _is_baserunning_text(txt):
        return "baserunning"
    return "other"


def _to_bool(value: Any) -> bool:
    if value in (None, "", 0, "0", "false", "False", False):
        return False
    return True


def _bases_from_state(cgs: Mapping[str, Any]) -> tuple[bool, bool, bool]:
    return (_to_bool(cgs.get("base1")), _to_bool(cgs.get("base2")), _to_bool(cgs.get("base3")))


def _normalize_player_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _new_stat_row(keys: Iterable[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _update_stat_row(target: dict[str, int], delta: Mapping[str, int]) -> None:
    for key, value in delta.items():
        target[key] = int(target.get(key, 0) or 0) + int(value or 0)


def _sum_stat_rows(rows: Mapping[str, Mapping[str, int]], keys: Iterable[str]) -> dict[str, int]:
    total = _new_stat_row(keys)
    for row in rows.values():
        _update_stat_row(total, row)
    return total


def _is_terminal_event(event: ScoringEvent) -> bool:
    return event.event_category == "bat_result"


def _event_has_batter_action(event: ScoringEvent) -> bool:
    return event.event_category in {"pitch", "bat_result"}


def _event_starts_new_pa(event: ScoringEvent) -> bool:
    if not event.batter_id:
        return False
    return _event_has_batter_action(event) or _is_batter_intro_text(event.text or "")


def _count_tuple(balls: int | None, strikes: int | None) -> tuple[int, int]:
    return (int(balls or 0), int(strikes or 0))


def _player_pos_text(player: Mapping[str, Any]) -> str:
    return str(player.get("playerPos") or player.get("position") or "")


def _is_pitcher_substitution(event: ScoringEvent) -> bool:
    text = event.text or ""
    if event.event_category == "substitution" and "투수" in text and "교체" in text:
        return True
    player_change = event.player_change or {}
    if player_change.get("type") != "substitution":
        return False
    in_player = player_change.get("inPlayer") or {}
    out_player = player_change.get("outPlayer") or {}
    return _player_pos_text(in_player) == "투수" or _player_pos_text(out_player) == "투수"


def _is_batter_substitution(event: ScoringEvent) -> bool:
    text = event.text or ""
    if event.event_category == "substitution" and "대타" in text and "교체" in text:
        return True
    player_change = event.player_change or {}
    if player_change.get("type") != "substitution":
        return False
    in_player = player_change.get("inPlayer") or {}
    out_player = player_change.get("outPlayer") or {}
    return "대타" in _player_pos_text(in_player) or "번타자" in _player_pos_text(out_player) or "대타" in text


def _append_batter_substitution(pa: PlateAppearanceContext, event: ScoringEvent, *, from_player_id: str | None, to_player_id: str | None) -> None:
    if from_player_id == to_player_id and from_player_id:
        return
    pa.batter_substitutions.append(
        SubstitutionSnapshot(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            balls=event.balls,
            strikes=event.strikes,
            seqno=event.seqno,
            text=event.text or "",
        )
    )
    pa.current_batter_id = to_player_id


def _append_pitcher_substitution(pa: PlateAppearanceContext, event: ScoringEvent, *, from_player_id: str | None, to_player_id: str | None) -> None:
    if from_player_id == to_player_id and from_player_id:
        return
    pa.pitcher_substitutions.append(
        SubstitutionSnapshot(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            balls=event.balls,
            strikes=event.strikes,
            seqno=event.seqno,
            text=event.text or "",
        )
    )
    pa.current_pitcher_id = to_player_id


def _apply_substitution_event(pa: PlateAppearanceContext | None, event: ScoringEvent) -> None:
    if pa is None:
        return

    player_change = event.player_change or {}
    in_player = player_change.get("inPlayer") or {}
    out_player = player_change.get("outPlayer") or {}
    in_player_id = _normalize_player_id(in_player.get("playerId") or in_player.get("playerCode"))
    out_player_id = _normalize_player_id(out_player.get("playerId") or out_player.get("playerCode"))

    if _is_batter_substitution(event):
        _append_batter_substitution(
            pa,
            event,
            from_player_id=out_player_id or pa.current_batter_id,
            to_player_id=in_player_id or event.batter_id,
        )

    if _is_pitcher_substitution(event):
        _append_pitcher_substitution(
            pa,
            event,
            from_player_id=out_player_id or pa.current_pitcher_id,
            to_player_id=in_player_id or event.pitcher_id,
        )


def _is_interference_text(text: str) -> bool:
    lowered = text.lower()
    return (
        ("타격방해" in text or "포수방해" in text or "interference" in lowered or "obstruction" in lowered)
        and "출루" in text
    )


def _is_hbp_text(text: str) -> bool:
    return "몸에 맞는 볼" in text


def _is_ibb_text(text: str) -> bool:
    return "자동 고의4구" in text or "고의4구" in text or "고의 4구" in text


def _is_walk_text(text: str) -> bool:
    return _is_ibb_text(text) or "볼넷" in text


def _is_sac_bunt_text(text: str) -> bool:
    return "희생번트" in text


def _is_sac_fly_text(text: str) -> bool:
    return "희생플라이" in text


def _is_hit_text(text: str) -> bool:
    return "홈런" in text or "3루타" in text or "2루타" in text or "1루타" in text or "안타" in text


def _is_home_run_text(text: str) -> bool:
    return "홈런" in text


def _is_reach_on_error_text(text: str) -> bool:
    return "실책" in text and "출루" in text and not _is_interference_text(text)


def _is_fielders_choice_text(text: str) -> bool:
    return "야수선택" in text or "포스아웃" in text or "땅볼로 출루" in text or "플라이로 출루" in text


def _is_double_play_text(text: str) -> bool:
    return "병살타" in text or "삼중살" in text


def _is_dropped_third_strike_text(text: str) -> bool:
    return "낫아웃" in text or "낫 아웃" in text or "스트라이크 낫아웃" in text or "스트라이크 낫 아웃" in text


def _is_foul_bunt_third_strike(pa: PlateAppearanceContext, text: str) -> bool:
    if "쓰리번트" in text:
        return True
    if "번트" not in text or "아웃" not in text:
        return False
    if not pa.pitch_events:
        return False
    last_pitch = pa.pitch_events[-1]
    return ("번트파울" in (last_pitch.text or "") or (last_pitch.pitch_result or "") == "W") and int(last_pitch.strikes or 0) == 2


def _is_strikeout_text(pa: PlateAppearanceContext, text: str) -> bool:
    return "삼진" in text or _is_dropped_third_strike_text(text) or _is_foul_bunt_third_strike(pa, text)


def _terminal_signature(event: ScoringEvent) -> tuple[Any, ...]:
    return (
        event.inning_no,
        event.half,
        event.batter_id,
        event.text,
        event.outs,
        event.balls,
        event.strikes,
        event.base1,
        event.base2,
        event.base3,
    )


def _base_batter_stats() -> dict[str, int]:
    return _new_stat_row(BATTER_STAT_KEYS)


def _batter_stats_from_terminal(
    *,
    category: str,
    ab: int = 0,
    hit: int = 0,
    bb: int = 0,
    ibb: int = 0,
    so: int = 0,
    hbp: int = 0,
    sh: int = 0,
    sf: int = 0,
    ci: int = 0,
    roe: int = 0,
    fc: int = 0,
    dp: int = 0,
    hr: int = 0,
) -> TerminalPAResult:
    stats = _base_batter_stats()
    stats["pa"] = 1
    stats["ab"] = ab
    stats["hit"] = hit
    stats["bb"] = bb
    stats["ibb"] = ibb
    stats["so"] = so
    stats["hbp"] = hbp
    stats["sh"] = sh
    stats["sf"] = sf
    stats["ci"] = ci
    stats["roe"] = roe
    stats["fc"] = fc
    stats["dp"] = dp
    stats["hr"] = hr
    return TerminalPAResult(category=category, stats=stats, is_walk=bb == 1, is_strikeout=so == 1)


def classify_terminal_pa_result(pa: PlateAppearanceContext, terminal_event: ScoringEvent) -> TerminalPAResult:
    text = terminal_event.text or ""

    if _is_interference_text(text):
        return _batter_stats_from_terminal(category="interference", ci=1)
    if _is_hbp_text(text):
        return _batter_stats_from_terminal(category="hit_by_pitch", hbp=1)
    if _is_ibb_text(text):
        return _batter_stats_from_terminal(category="intentional_walk", bb=1, ibb=1)
    if _is_walk_text(text):
        return _batter_stats_from_terminal(category="walk", bb=1)
    if _is_sac_fly_text(text):
        result = _batter_stats_from_terminal(category="sacrifice_fly", sf=1)
        if _is_reach_on_error_text(text):
            result.stats["roe"] = 1
        return result
    if _is_sac_bunt_text(text):
        result = _batter_stats_from_terminal(category="sacrifice_bunt", sh=1)
        if _is_reach_on_error_text(text):
            result.stats["roe"] = 1
        if _is_fielders_choice_text(text):
            result.stats["fc"] = 1
        return result
    if _is_strikeout_text(pa, text):
        return _batter_stats_from_terminal(category="strikeout", ab=1, so=1)
    if _is_home_run_text(text):
        return _batter_stats_from_terminal(category="home_run", ab=1, hit=1, hr=1)
    if _is_hit_text(text):
        return _batter_stats_from_terminal(category="hit", ab=1, hit=1)
    if _is_reach_on_error_text(text):
        return _batter_stats_from_terminal(category="reach_on_error", ab=1, roe=1, dp=int(_is_double_play_text(text)))
    if _is_fielders_choice_text(text):
        return _batter_stats_from_terminal(category="fielders_choice", ab=1, fc=1, dp=int(_is_double_play_text(text)))
    if _is_double_play_text(text):
        return _batter_stats_from_terminal(category="double_play", ab=1, dp=1)
    if "아웃" in text:
        return _batter_stats_from_terminal(category="out", ab=1)
    return _batter_stats_from_terminal(category="unknown", ab=1)


def classify_terminal_pa_text(text: str) -> TerminalPAResult:
    dummy_event = ScoringEvent(
        inning_no=0,
        half="top",
        seqno=0,
        type_code=13,
        event_category="bat_result",
        text=text or "",
        batter_id=None,
        pitcher_id=None,
        balls=None,
        strikes=None,
        outs=None,
        base1=False,
        base2=False,
        base3=False,
        pitch_num=None,
        pitch_result=None,
        pts_pitch_id=None,
        player_change={},
        raw_payload={},
    )
    dummy_pa = PlateAppearanceContext(
        inning_no=0,
        half="top",
        offense_side="away",
        defense_side="home",
        start_seqno=0,
        starting_batter_id=None,
        current_batter_id=None,
        starting_pitcher_id=None,
        current_pitcher_id=None,
    )
    return classify_terminal_pa_result(dummy_pa, dummy_event)


def resolve_batter_credit_owner(pa: PlateAppearanceContext, result: TerminalPAResult, terminal_event: ScoringEvent) -> tuple[str | None, tuple[int | None, int | None] | None]:
    finishing_batter_id = terminal_event.batter_id or pa.current_batter_id or pa.starting_batter_id
    if not result.is_strikeout:
        return finishing_batter_id, None

    for substitution in reversed(pa.batter_substitutions):
        if substitution.to_player_id == finishing_batter_id and int(substitution.strikes or 0) == 2:
            return substitution.from_player_id or finishing_batter_id, (substitution.balls, substitution.strikes)
    return finishing_batter_id, None


def resolve_pitcher_credit_owner(pa: PlateAppearanceContext, result: TerminalPAResult, terminal_event: ScoringEvent) -> tuple[str | None, tuple[int | None, int | None] | None]:
    finishing_pitcher_id = terminal_event.pitcher_id or pa.current_pitcher_id or pa.starting_pitcher_id
    if not result.is_walk:
        return finishing_pitcher_id, None

    for substitution in reversed(pa.pitcher_substitutions):
        if substitution.to_player_id != finishing_pitcher_id:
            continue
        if _count_tuple(substitution.balls, substitution.strikes) in HITTER_ADVANTAGE_COUNTS:
            return substitution.from_player_id or finishing_pitcher_id, (substitution.balls, substitution.strikes)
        return finishing_pitcher_id, None
    return finishing_pitcher_id, None


def _pitcher_stats_from_batter_stats(batter_stats: Mapping[str, int]) -> dict[str, int]:
    stats = _new_stat_row(PITCHER_STAT_KEYS)
    stats["bf"] = int(batter_stats.get("pa", 0) or 0)
    stats["pa"] = int(batter_stats.get("pa", 0) or 0)
    stats["ab"] = int(batter_stats.get("ab", 0) or 0)
    stats["hit"] = int(batter_stats.get("hit", 0) or 0)
    stats["bb"] = int(batter_stats.get("bb", 0) or 0)
    stats["ibb"] = int(batter_stats.get("ibb", 0) or 0)
    stats["so"] = int(batter_stats.get("so", 0) or 0)
    stats["hbp"] = int(batter_stats.get("hbp", 0) or 0)
    stats["hr"] = int(batter_stats.get("hr", 0) or 0)
    stats["bbhp"] = stats["bb"] + stats["hbp"]
    return stats


def score_plate_appearance(pa: PlateAppearanceContext, terminal_event: ScoringEvent) -> ScoredPlateAppearance:
    result = classify_terminal_pa_result(pa, terminal_event)
    batter_owner_id, batter_sub_count = resolve_batter_credit_owner(pa, result, terminal_event)
    pitcher_owner_id, pitcher_sub_count = resolve_pitcher_credit_owner(pa, result, terminal_event)
    pitcher_stats = _pitcher_stats_from_batter_stats(result.stats)
    return ScoredPlateAppearance(
        inning_no=pa.inning_no,
        half=pa.half,
        offense_side=pa.offense_side,
        defense_side=pa.defense_side,
        start_seqno=pa.start_seqno,
        end_seqno=terminal_event.seqno,
        is_terminal=True,
        result_text=terminal_event.text or "",
        official_result_category=result.category,
        starting_batter_id=pa.starting_batter_id,
        finishing_batter_id=terminal_event.batter_id or pa.current_batter_id or pa.starting_batter_id,
        batter_credit_owner_id=batter_owner_id,
        starting_pitcher_id=pa.starting_pitcher_id,
        finishing_pitcher_id=terminal_event.pitcher_id or pa.current_pitcher_id or pa.starting_pitcher_id,
        pitcher_credit_owner_id=pitcher_owner_id,
        batter_substitution_count=batter_sub_count,
        pitcher_substitution_count=pitcher_sub_count,
        batter_stats=dict(result.stats),
        pitcher_stats=pitcher_stats,
    )


def _start_pa_from_event(event: ScoringEvent) -> PlateAppearanceContext:
    return PlateAppearanceContext(
        inning_no=event.inning_no,
        half=event.half,
        offense_side=event.offense_side,
        defense_side=event.defense_side,
        start_seqno=event.seqno,
        starting_batter_id=event.batter_id,
        current_batter_id=event.batter_id,
        starting_pitcher_id=event.pitcher_id,
        current_pitcher_id=event.pitcher_id,
        end_seqno=event.seqno,
    )


def _partial_plate_appearance(pa: PlateAppearanceContext) -> ScoredPlateAppearance:
    return ScoredPlateAppearance(
        inning_no=pa.inning_no,
        half=pa.half,
        offense_side=pa.offense_side,
        defense_side=pa.defense_side,
        start_seqno=pa.start_seqno,
        end_seqno=pa.end_seqno or pa.start_seqno,
        is_terminal=False,
        result_text="",
        official_result_category=None,
        starting_batter_id=pa.starting_batter_id,
        finishing_batter_id=pa.current_batter_id,
        batter_credit_owner_id=None,
        starting_pitcher_id=pa.starting_pitcher_id,
        finishing_pitcher_id=pa.current_pitcher_id,
        pitcher_credit_owner_id=None,
        batter_substitution_count=None,
        pitcher_substitution_count=None,
        batter_stats=_base_batter_stats(),
        pitcher_stats=_new_stat_row(PITCHER_STAT_KEYS),
    )


def score_scoring_events(events: Iterable[ScoringEvent]) -> PAScoringSummary:
    terminal_count = 0
    partial_count = 0
    scored_pas: list[ScoredPlateAppearance] = []
    batter_rows = {"home": {}, "away": {}}
    pitcher_rows = {"home": {}, "away": {}}
    current_pa: PlateAppearanceContext | None = None
    last_terminal_signature: tuple[Any, ...] | None = None

    def batter_bucket(side: str, player_id: str | None) -> dict[str, int] | None:
        if not player_id:
            return None
        if player_id not in batter_rows[side]:
            batter_rows[side][player_id] = _base_batter_stats()
        return batter_rows[side][player_id]

    def pitcher_bucket(side: str, player_id: str | None) -> dict[str, int] | None:
        if not player_id:
            return None
        if player_id not in pitcher_rows[side]:
            pitcher_rows[side][player_id] = _new_stat_row(PITCHER_STAT_KEYS)
        return pitcher_rows[side][player_id]

    def finalize_partial_pa() -> None:
        nonlocal current_pa, partial_count
        if current_pa and current_pa.has_batter_action:
            partial_count += 1
            scored_pas.append(_partial_plate_appearance(current_pa))
        current_pa = None

    for event in events:
        if current_pa and current_pa.in_key != event.in_key:
            finalize_partial_pa()

        if _is_terminal_event(event):
            signature = _terminal_signature(event)
            if signature == last_terminal_signature:
                continue

        _apply_substitution_event(current_pa, event)

        starts_new_pa = _event_starts_new_pa(event)
        current_count = _count_tuple(event.balls, event.strikes)
        implicit_mid_pa_batter_change = (
            current_pa is not None
            and current_pa.in_key == event.in_key
            and event.batter_id
            and event.batter_id != current_pa.current_batter_id
            and current_pa.has_batter_action
            and current_count != (0, 0)
        )
        implicit_mid_pa_pitcher_change = (
            current_pa is not None
            and current_pa.in_key == event.in_key
            and event.pitcher_id
            and event.pitcher_id != current_pa.current_pitcher_id
            and current_pa.has_batter_action
            and current_count != (0, 0)
        )

        if implicit_mid_pa_batter_change:
            _append_batter_substitution(
                current_pa,
                event,
                from_player_id=current_pa.current_batter_id,
                to_player_id=event.batter_id,
            )

        if implicit_mid_pa_pitcher_change:
            _append_pitcher_substitution(
                current_pa,
                event,
                from_player_id=current_pa.current_pitcher_id,
                to_player_id=event.pitcher_id,
            )

        if starts_new_pa:
            if current_pa is None:
                current_pa = _start_pa_from_event(event)
            elif current_pa.in_key == event.in_key and current_pa.current_batter_id == event.batter_id:
                current_pa.end_seqno = event.seqno
            elif current_pa.in_key == event.in_key and not current_pa.has_batter_action:
                current_pa = _start_pa_from_event(event)
            elif implicit_mid_pa_batter_change:
                current_pa.end_seqno = event.seqno
            else:
                finalize_partial_pa()
                current_pa = _start_pa_from_event(event)

        if current_pa is None:
            continue

        current_pa.end_seqno = event.seqno
        if _event_has_batter_action(event):
            current_pa.has_batter_action = True
        if event.event_category == "pitch":
            current_pa.pitch_events.append(event)

        if not _is_terminal_event(event):
            continue

        scored_pa = score_plate_appearance(current_pa, event)
        scored_pas.append(scored_pa)
        terminal_count += 1
        last_terminal_signature = _terminal_signature(event)

        batter_row = batter_bucket(scored_pa.offense_side, scored_pa.batter_credit_owner_id)
        if batter_row is not None:
            _update_stat_row(batter_row, scored_pa.batter_stats)

        pitcher_row = pitcher_bucket(scored_pa.defense_side, scored_pa.pitcher_credit_owner_id)
        if pitcher_row is not None:
            _update_stat_row(pitcher_row, scored_pa.pitcher_stats)

        current_pa = None

    finalize_partial_pa()

    return PAScoringSummary(
        terminal_plate_appearances=terminal_count,
        partial_plate_appearances=partial_count,
        scored_plate_appearances=scored_pas,
        batter_totals_by_side={
            "home": {player_id: dict(row) for player_id, row in batter_rows["home"].items()},
            "away": {player_id: dict(row) for player_id, row in batter_rows["away"].items()},
        },
        batter_team_totals={
            "home": _sum_stat_rows(batter_rows["home"], BATTER_STAT_KEYS),
            "away": _sum_stat_rows(batter_rows["away"], BATTER_STAT_KEYS),
        },
        pitcher_totals_by_side={
            "home": {player_id: dict(row) for player_id, row in pitcher_rows["home"].items()},
            "away": {player_id: dict(row) for player_id, row in pitcher_rows["away"].items()},
        },
        pitcher_team_totals={
            "home": _sum_stat_rows(pitcher_rows["home"], PITCHER_STAT_KEYS),
            "away": _sum_stat_rows(pitcher_rows["away"], PITCHER_STAT_KEYS),
        },
    )


def iter_scoring_events_from_relay(relay: list[Any]) -> Iterable[ScoringEvent]:
    for inning in relay or []:
        for block in inning or []:
            half = _normalize_half(block.get("homeOrAway"))
            if half is None:
                continue
            inning_no = to_int(block.get("inn"))
            for event in block.get("textOptions") or []:
                current_game_state = event.get("currentGameState") or {}
                pitch_id = event.get("ptsPitchId")
                b1, b2, b3 = _bases_from_state(current_game_state)
                yield ScoringEvent(
                    inning_no=inning_no,
                    half=half,
                    seqno=to_int(event.get("seqno")),
                    type_code=to_int(event.get("type"), None),
                    event_category=classify_event(
                        event.get("text") or "",
                        to_int(event.get("pitchNum"), None),
                        event.get("pitchResult"),
                        str(pitch_id) if pitch_id not in (None, "") else None,
                        event.get("playerChange"),
                        to_int(event.get("type"), None),
                    ),
                    text=event.get("text") or "",
                    batter_id=_normalize_player_id(current_game_state.get("batter") or (event.get("batterRecord") or {}).get("pcode")),
                    pitcher_id=_normalize_player_id(current_game_state.get("pitcher")),
                    balls=to_int(current_game_state.get("ball"), None),
                    strikes=to_int(current_game_state.get("strike"), None),
                    outs=to_int(current_game_state.get("out"), None),
                    base1=b1,
                    base2=b2,
                    base3=b3,
                    pitch_num=to_int(event.get("pitchNum"), None),
                    pitch_result=event.get("pitchResult"),
                    pts_pitch_id=str(pitch_id) if pitch_id not in (None, "") else None,
                    player_change=event.get("playerChange") or {},
                    raw_payload=event,
                )


def scoring_event_from_mapping(row: Mapping[str, Any]) -> ScoringEvent:
    raw_payload = dict(row.get("raw_payload") or {})
    player_change = raw_payload.get("playerChange") or row.get("player_change") or {}
    pitch_id = raw_payload.get("ptsPitchId") or row.get("pts_pitch_id")
    return ScoringEvent(
        inning_no=int(row.get("inning_no") or 0),
        half=str(row.get("half") or ""),
        seqno=int(row.get("seqno") or 0),
        type_code=to_int(row.get("type_code"), None),
        event_category=str(row.get("event_category") or ""),
        text=str(row.get("text") or raw_payload.get("text") or ""),
        batter_id=_normalize_player_id(row.get("batter_id")),
        pitcher_id=_normalize_player_id(row.get("pitcher_id")),
        balls=to_int(row.get("balls"), None),
        strikes=to_int(row.get("strikes"), None),
        outs=to_int(row.get("outs"), None),
        base1=bool(row.get("base1")),
        base2=bool(row.get("base2")),
        base3=bool(row.get("base3")),
        pitch_num=to_int(raw_payload.get("pitchNum"), None),
        pitch_result=raw_payload.get("pitchResult"),
        pts_pitch_id=str(pitch_id) if pitch_id not in (None, "") else None,
        player_change=player_change,
        raw_payload=raw_payload,
    )


def score_relay_plate_appearances(relay: list[Any]) -> PAScoringSummary:
    return score_scoring_events(iter_scoring_events_from_relay(relay))
