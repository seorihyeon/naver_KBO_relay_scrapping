from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.normalize_game import (
    EventRec,
    _event_starts_new_pa,
    _is_pa_end,
    _is_batter_intro_text,
    _normalized_pitch_id,
    _resolve_baserunning_subject,
    classify_event,
)


def make_event(**overrides) -> EventRec:
    data = {
        "raw_event_id": 1,
        "raw_block_id": 1,
        "inning_no": 1,
        "half": "top",
        "seqno": 1,
        "type_code": None,
        "text": "",
        "batter_id": "100",
        "pitcher_id": "200",
        "outs": 0,
        "balls": 0,
        "strikes": 0,
        "base1": False,
        "base2": False,
        "base3": False,
        "home_score": 0,
        "away_score": 0,
        "home_hits": 0,
        "away_hits": 0,
        "home_errors": 0,
        "away_errors": 0,
        "home_ball_four": 0,
        "away_ball_four": 0,
        "pitch_num": None,
        "pitch_result": None,
        "pts_pitch_id": None,
        "speed_kph": None,
        "stuff_text": None,
        "category": "other",
        "raw_payload": {},
    }
    data.update(overrides)
    return EventRec(**data)


def test_classify_pitch_event():
    assert classify_event("\uc9c1\uad6c \uc2a4\ud2b8\ub77c\uc774\ud06c", pitch_num=1, pitch_result="\uc2a4\ud2b8\ub77c\uc774\ud06c", pts_pitch_id="123", player_change=None, type_code=1) == "pitch"


def test_classify_review_event():
    assert classify_event("\ube44\ub514\uc624 \ud310\ub3c5 \uacb0\uacfc \uc544\uc6c3 \uc720\uc9c0", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=None) == "review"


def test_classify_substitution_event():
    assert classify_event("\ud22c\uc218 \uad50\uccb4", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change={"in": "A"}, type_code=2) == "substitution"


def test_classify_baserunning_event():
    assert classify_event("1\ub8e8\uc8fc\uc790 \ub3c4\ub8e8 \uc131\uacf5", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=14) == "baserunning"


def test_classify_batter_result_event_for_hit_text():
    assert classify_event("\ucd5c\uc8fc\ud658 : \uc6b0\uc775\uc218 \ub4a4 3\ub8e8\ud0c0", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=13) == "bat_result"


def test_classify_batter_result_event_for_out_text():
    text = "\uae40\ud61c\uc131 : \uc720\uaca9\uc218 \ub545\ubcfc \uc544\uc6c3 (\uc720\uaca9\uc218->1\ub8e8\uc218 \uc1a1\uad6c\uc544\uc6c3)"
    assert classify_event(text, pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=13) == "bat_result"


def test_classify_type_13_with_pitch_metadata_still_as_bat_result():
    text = "\uae40\ud61c\uc131 : \uc88c\uc804 \uc548\ud0c0"
    assert classify_event(text, pitch_num=3, pitch_result="X", pts_pitch_id="pitch-3", player_change=None, type_code=13) == "bat_result"


def test_classify_pickoff_attempt_as_baserunning():
    assert classify_event("1\ub8e8 \uacac\uc81c \uc2dc\ub3c4", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=None) == "baserunning"


def test_classify_automatic_intentional_walk_as_bat_result():
    assert classify_event("\ub85c\ud558\uc2a4 : \uc790\ub3d9 \uace0\uc7584\uad6c", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=23) == "bat_result"


def test_classify_spaced_not_out_as_bat_result():
    text = "\uc774\uc8fc\ud615 : \ud3ec\uc218 \uc2a4\ud2b8\ub77c\uc774\ud06c \ub0ab \uc544\uc6c3 (\ud3ec\uc218->1\ub8e8\uc218 1\ub8e8 \ud130\uce58\uc544\uc6c3)"
    assert classify_event(text, pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=13) == "bat_result"


def test_classify_type_13_dropped_third_strike_as_bat_result_even_with_tag_out_text():
    text = "\ubc15\ubbfc\uc6b0 : \ud3ec\uc218 \uc2a4\ud2b8\ub77c\uc774\ud06c \ub0ab \uc544\uc6c3 (\ud3ec\uc218 \ud0dc\uadf8\uc544\uc6c3)"
    assert classify_event(text, pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None, type_code=13) == "bat_result"


def test_is_pa_end_for_real_batter_result_text():
    event = make_event(
        text="\uc548\uc0c1\ud604 : \uc6b0\uc775\uc218 \ub4a4 1\ub8e8\ud0c0",
        category="bat_result",
    )
    assert _is_pa_end(event)


def test_normalized_pitch_id_is_namespaced_by_game():
    assert _normalized_pitch_id(101, "240324_141220") == "101:240324_141220"


def test_batter_intro_text_detection():
    assert _is_batter_intro_text("4\ubc88\ud0c0\uc790 \ub178\uc2dc\ud658")
    assert _is_batter_intro_text("\ub300\ud0c0 \ud64d\ucc3d\uae30")
    assert not _is_batter_intro_text("1\ub8e8\uc8fc\uc790 \ud669\uc601\ubb35 : \ud648\uc778")


def test_event_starts_new_pa_for_intro_and_action_events():
    intro_event = make_event(text="4\ubc88\ud0c0\uc790 \ub178\uc2dc\ud658", category="other")
    action_event = make_event(text="1\uad6c \ud53c\uce58\ud074\ub77d \ud22c\uc218\uc704\ubc18 \ubcfc", category="other")
    header_event = make_event(text="1\ud68c\ub9d0 \ub86f\ub370 \uacf5\uaca9", category="header")
    neutral_pickoff_event = make_event(text="1\ub8e8 \uacac\uc81c \uc2dc\ub3c4", category="baserunning")
    substitution_event = make_event(text="\ud22c\uc218 \uad50\uccb4", category="substitution")

    assert _event_starts_new_pa(intro_event)
    assert _event_starts_new_pa(action_event)
    assert not _event_starts_new_pa(header_event)
    assert not _event_starts_new_pa(neutral_pickoff_event)
    assert not _event_starts_new_pa(substitution_event)


def test_is_pa_end_ignores_follow_up_baserunning_and_review_text():
    baserunning_event = make_event(text="1\ub8e8\uc8fc\uc790 \ubb38\uc0c1\ucca0 : \ub3c4\ub8e8\uc2e4\ud328\uc544\uc6c3", category="baserunning")
    review_event = make_event(text="KT\uc694\uccad \ube44\ub514\uc624 \ud310\ub3c5", category="review")

    assert not _is_pa_end(baserunning_event)
    assert not _is_pa_end(review_event)


def test_resolve_baserunning_subject_prefers_named_runner():
    event = make_event(
        text="1\ub8e8\uc8fc\uc790 \ud669\uc601\ubb35 : \ud648\uc778",
        category="baserunning",
        batter_id="53764",
    )
    player_name_by_id = {"53764": "\ubb38\ud604\ube48", "54795": "\ud669\uc601\ubb35"}
    name_to_player_id = {"\ubb38\ud604\ube48": "53764", "\ud669\uc601\ubb35": "54795"}

    runner_id, runner_name = _resolve_baserunning_subject(event, player_name_by_id, name_to_player_id)

    assert runner_id == "54795"
    assert runner_name == "\ud669\uc601\ubb35"


def test_resolve_baserunning_subject_falls_back_to_batter_for_batter_runner():
    event = make_event(
        text="\ubc15\ubbfc\uc6b0 : \ud22c\uc218 \ub545\ubcfc \uc544\uc6c3",
        category="baserunning",
        batter_id="62907",
    )
    player_name_by_id = {"62907": "\ubc15\ubbfc\uc6b0"}
    name_to_player_id = {"\ubc15\ubbfc\uc6b0": "62907"}

    runner_id, runner_name = _resolve_baserunning_subject(event, player_name_by_id, name_to_player_id)

    assert runner_id == "62907"
    assert runner_name == "\ubc15\ubbfc\uc6b0"
