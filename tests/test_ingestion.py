from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.normalize_game import classify_event


def test_classify_pitch_event():
    assert classify_event("직구 스트라이크", pitch_num=1, pitch_result="스트라이크", pts_pitch_id="123", player_change=None) == "pitch"


def test_classify_review_event():
    assert classify_event("비디오 판독 결과 아웃 유지", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None) == "review"


def test_classify_substitution_event():
    assert classify_event("투수 교체", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change={"in": "A"}) == "substitution"


def test_classify_baserunning_event():
    assert classify_event("1루주자 도루 성공", pitch_num=None, pitch_result=None, pts_pitch_id=None, player_change=None) == "baserunning"
