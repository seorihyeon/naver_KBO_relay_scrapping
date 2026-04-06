from pathlib import Path
import json
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from check_data import (
    build_batter_stats_from_relay,
    build_pitcher_stats_from_relay,
    extract_record_batters,
    extract_record_pitchers,
)
from src.kbo_ingest.pa_scoring import ScoringEvent, classify_terminal_pa_text, score_scoring_events


def make_event(
    *,
    seqno: int,
    inning_no: int = 1,
    half: str = "top",
    event_category: str,
    text: str,
    batter_id: str = "100",
    pitcher_id: str = "200",
    balls: int | None = 0,
    strikes: int | None = 0,
    outs: int | None = 0,
    type_code: int | None = None,
    player_change: dict | None = None,
    pitch_num: int | None = None,
    pitch_result: str | None = None,
) -> ScoringEvent:
    if type_code is None and event_category == "bat_result":
        type_code = 13
    return ScoringEvent(
        inning_no=inning_no,
        half=half,
        seqno=seqno,
        type_code=type_code,
        event_category=event_category,
        text=text,
        batter_id=batter_id,
        pitcher_id=pitcher_id,
        balls=balls,
        strikes=strikes,
        outs=outs,
        base1=False,
        base2=False,
        base3=False,
        pitch_num=pitch_num,
        pitch_result=pitch_result,
        pts_pitch_id=None,
        player_change=player_change or {},
        raw_payload={},
    )


def make_batter_change(seqno: int, *, from_batter: str, to_batter: str, balls: int, strikes: int) -> ScoringEvent:
    return make_event(
        seqno=seqno,
        event_category="substitution",
        text="\ub300\ud0c0 \uad50\uccb4",
        batter_id=to_batter,
        balls=balls,
        strikes=strikes,
        player_change={
            "type": "substitution",
            "inPlayer": {"playerId": to_batter, "playerPos": "\ub300\ud0c0"},
            "outPlayer": {"playerId": from_batter, "playerPos": "\ud0c0\uc790"},
        },
    )


def make_pitcher_change(seqno: int, *, from_pitcher: str, to_pitcher: str, balls: int, strikes: int) -> ScoringEvent:
    return make_event(
        seqno=seqno,
        event_category="substitution",
        text="\ud22c\uc218 \uad50\uccb4",
        pitcher_id=to_pitcher,
        balls=balls,
        strikes=strikes,
        player_change={
            "type": "substitution",
            "inPlayer": {"playerId": to_pitcher, "playerPos": "\ud22c\uc218"},
            "outPlayer": {"playerId": from_pitcher, "playerPos": "\ud22c\uc218"},
        },
    )


def load_payload(path_text: str) -> dict:
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


def test_foul_bunt_third_strike_context_counts_as_strikeout():
    summary = score_scoring_events(
        [
            make_event(
                seqno=1,
                event_category="pitch",
                text="\ubc88\ud2b8\ud30c\uc6b8",
                pitch_num=3,
                pitch_result="\ud30c\uc6b8",
                strikes=2,
            ),
            make_event(
                seqno=2,
                event_category="bat_result",
                text="\ud0c0\uc790 : \ud3ec\uc218 \ubc88\ud2b8 \uc544\uc6c3",
                strikes=2,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.official_result_category == "strikeout"
    assert pa.batter_stats["so"] == 1
    assert pa.batter_stats["ab"] == 1


def test_dropped_third_strike_with_wild_pitch_still_counts_strikeout():
    result = classify_terminal_pa_text("\ud0c0\uc790 : \ud3ec\uc218 \uc2a4\ud2b8\ub77c\uc774\ud06c \ub0ab \uc544\uc6c3, \ud3ed\ud22c\ub85c 1\ub8e8 \ucd9c\ub8e8")

    assert result.category == "strikeout"
    assert result.stats["pa"] == 1
    assert result.stats["ab"] == 1
    assert result.stats["so"] == 1


@pytest.mark.parametrize(
    ("text", "stat_key", "expected_ibb"),
    [
        ("\ud0c0\uc790 : \ubcfc\ub137", "bb", 0),
        ("\ud0c0\uc790 : \uace0\uc7584\uad6c", "bb", 1),
        ("\ud0c0\uc790 : \uc790\ub3d9 \uace0\uc7584\uad6c", "bb", 1),
        ("\ud0c0\uc790 : \ubab8\uc5d0 \ub9de\ub294 \ubcfc", "hbp", 0),
    ],
)
def test_walk_family_and_hbp_do_not_count_as_at_bats(text: str, stat_key: str, expected_ibb: int):
    result = classify_terminal_pa_text(text)

    assert result.stats["pa"] == 1
    assert result.stats["ab"] == 0
    assert result.stats[stat_key] == 1
    assert result.stats["ibb"] == expected_ibb


def test_two_strike_pinch_hitter_strikeout_is_credited_to_previous_batter():
    summary = score_scoring_events(
        [
            make_event(seqno=1, event_category="pitch", text="0-2 pitch", strikes=2, pitch_num=2),
            make_batter_change(seqno=2, from_batter="100", to_batter="101", balls=0, strikes=2),
            make_event(
                seqno=3,
                event_category="bat_result",
                text="\ud0c0\uc790 : \uc0bc\uc9c4 \uc544\uc6c3",
                batter_id="101",
                strikes=2,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.batter_credit_owner_id == "100"
    assert summary.batter_totals_by_side["away"]["100"]["ab"] == 1
    assert summary.batter_totals_by_side["away"]["100"]["so"] == 1
    assert "101" not in summary.batter_totals_by_side["away"]


def test_two_strike_pinch_hitter_walk_stays_with_substitute_batter():
    summary = score_scoring_events(
        [
            make_event(seqno=1, event_category="pitch", text="0-2 pitch", strikes=2, pitch_num=2),
            make_batter_change(seqno=2, from_batter="100", to_batter="101", balls=0, strikes=2),
            make_event(
                seqno=3,
                event_category="bat_result",
                text="\ud0c0\uc790 : \ubcfc\ub137",
                batter_id="101",
                strikes=2,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.batter_credit_owner_id == "101"
    assert summary.batter_totals_by_side["away"]["101"]["pa"] == 1
    assert summary.batter_totals_by_side["away"]["101"]["bb"] == 1
    assert summary.batter_totals_by_side["away"]["101"]["ab"] == 0
    assert "100" not in summary.batter_totals_by_side["away"]


def test_catcher_interference_counts_plate_appearance_but_not_at_bat():
    result = classify_terminal_pa_text("\ud0c0\uc790 : \ud3ec\uc218 \ud0c0\uaca9\ubc29\ud574\ub85c 1\ub8e8 \ucd9c\ub8e8")

    assert result.stats["pa"] == 1
    assert result.stats["ab"] == 0
    assert result.stats["ci"] == 1
    assert result.stats["hit"] == 0
    assert result.stats["bb"] == 0
    assert result.stats["so"] == 0


@pytest.mark.parametrize(
    ("text", "stat_key"),
    [
        ("\ud0c0\uc790 : \ud22c\uc218 \ud76c\uc0dd\ubc88\ud2b8 \uc544\uc6c3", "sh"),
        ("\ud0c0\uc790 : \uc911\uacac\uc218 \ud76c\uc0dd\ud50c\ub77c\uc774 \uc544\uc6c3", "sf"),
    ],
)
def test_sacrifice_results_count_as_pa_but_not_ab(text: str, stat_key: str):
    result = classify_terminal_pa_text(text)

    assert result.stats["pa"] == 1
    assert result.stats["ab"] == 0
    assert result.stats[stat_key] == 1


@pytest.mark.parametrize(
    ("text", "stat_key"),
    [
        ("\ud0c0\uc790 : \uc720\uaca9\uc218 \uc2e4\ucc45\ub85c \ucd9c\ub8e8", "roe"),
        ("\ud0c0\uc790 : \uc720\uaca9\uc218 \ub545\ubcfc\ub85c \ucd9c\ub8e8", "fc"),
    ],
)
def test_reach_on_error_and_fielders_choice_count_as_at_bats(text: str, stat_key: str):
    result = classify_terminal_pa_text(text)

    assert result.stats["pa"] == 1
    assert result.stats["ab"] == 1
    assert result.stats[stat_key] == 1


def test_mid_count_pitcher_change_walk_is_credited_to_previous_pitcher_in_hitter_advantage_count():
    summary = score_scoring_events(
        [
            make_event(seqno=1, event_category="pitch", text="2-0 pitch", balls=2, strikes=0, pitch_num=2),
            make_pitcher_change(seqno=2, from_pitcher="200", to_pitcher="201", balls=2, strikes=0),
            make_event(
                seqno=3,
                event_category="bat_result",
                text="\ud0c0\uc790 : \ubcfc\ub137",
                pitcher_id="201",
                balls=4,
                strikes=0,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.pitcher_credit_owner_id == "200"
    assert summary.pitcher_totals_by_side["home"]["200"]["bb"] == 1
    assert "201" not in summary.pitcher_totals_by_side["home"]


def test_mid_count_pitcher_change_non_walk_is_credited_to_reliever():
    summary = score_scoring_events(
        [
            make_event(seqno=1, event_category="pitch", text="3-1 pitch", balls=3, strikes=1, pitch_num=4),
            make_pitcher_change(seqno=2, from_pitcher="200", to_pitcher="201", balls=3, strikes=1),
            make_event(
                seqno=3,
                event_category="bat_result",
                text="\ud0c0\uc790 : \uc88c\uc804 \uc548\ud0c0",
                pitcher_id="201",
                balls=3,
                strikes=1,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.pitcher_credit_owner_id == "201"
    assert summary.pitcher_totals_by_side["home"]["201"]["hit"] == 1
    assert summary.pitcher_totals_by_side["home"]["201"]["ab"] == 1
    assert "200" not in summary.pitcher_totals_by_side["home"]


def test_batter_and_pitcher_credit_owners_are_resolved_independently():
    summary = score_scoring_events(
        [
            make_event(seqno=1, event_category="pitch", text="0-2 pitch", balls=0, strikes=2, pitch_num=2),
            make_batter_change(seqno=2, from_batter="100", to_batter="101", balls=0, strikes=2),
            make_pitcher_change(seqno=3, from_pitcher="200", to_pitcher="201", balls=0, strikes=2),
            make_event(
                seqno=4,
                event_category="bat_result",
                text="\ud0c0\uc790 : \uc0bc\uc9c4 \uc544\uc6c3",
                batter_id="101",
                pitcher_id="201",
                balls=0,
                strikes=2,
            ),
        ]
    )

    pa = summary.scored_plate_appearances[-1]
    assert pa.batter_credit_owner_id == "100"
    assert pa.pitcher_credit_owner_id == "201"
    assert summary.batter_totals_by_side["away"]["100"]["so"] == 1
    assert summary.pitcher_totals_by_side["home"]["201"]["so"] == 1


@pytest.mark.parametrize(
    ("path_text", "side", "player_id", "stat_names"),
    [
        ("games/2025/20250913WOHH02025.json", "away", "69332", ("so",)),
        ("games/2024/20240625NCWO02024.json", "home", "62332", ("so",)),
        ("games/2024/20240502WOLT02024.json", "away", "62332", ("so",)),
        ("games/2025/20250517WONC22025.json", "away", "62332", ("so",)),
        ("games/2025/20250529LTSS02025.json", "home", "69418", ("so",)),
        ("games/2025/20250919LTNC02025.json", "home", "66606", ("ab", "so")),
        ("games/2025/20250919LTNC02025.json", "home", "67905", ("ab", "so")),
        ("games/2025/20250406HHSS02025.json", "away", "50704", ("ab", "so")),
        ("games/2025/20250406HHSS02025.json", "away", "66657", ("ab", "so")),
        ("games/2024/20240430SKHH02024.json", "home", "50704", ("ab", "so")),
        ("games/2024/20240430SKHH02024.json", "home", "54730", ("ab", "so")),
        ("games/2024/20240623HHHT22024.json", "home", "62947", ("ab",)),
        ("games/2025/20250725SKHH02025.json", "home", "54795", ("ab",)),
    ],
)
def test_reported_batter_regressions_match_record_totals(path_text: str, side: str, player_id: str, stat_names: tuple[str, ...]):
    payload = load_payload(path_text)
    relay_stats = build_batter_stats_from_relay(payload["relay"])
    record_stats = extract_record_batters(payload["record"]["batter"])
    relay_row = relay_stats[side].get(player_id, {})
    record_row = record_stats[side][player_id]

    for stat_name in stat_names:
        assert int(relay_row.get(stat_name, 0) or 0) == int(record_row.get(stat_name, 0) or 0)


def test_reported_pitcher_credit_regression_matches_record_totals():
    payload = load_payload("games/2024/20240407KTLG02024.json")
    relay_stats = build_pitcher_stats_from_relay(payload["relay"])
    record_stats = extract_record_pitchers(payload["record"]["pitcher"])

    assert relay_stats["away"]["69068"]["bb"] == record_stats["away"]["69068"]["bb"]
    assert relay_stats["away"]["69068"]["bbhp"] == record_stats["away"]["69068"]["bbhp"]
    assert relay_stats["away"]["66047"]["bb"] == record_stats["away"]["66047"]["bb"]
