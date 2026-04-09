import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.game_json import minimize_game_payload, pretty_game_json
from src.kbo_ingest.game_validation import validate_game
from src.kbo_ingest.source_profile import build_source_profile


def load_real_payload(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"실데이터 fixture가 없어 건너뜁니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def test_minimize_game_payload_strips_unused_fields():
    raw_payload = {
        "lineup": {
            "game_info": {
                "gdate": 20260406,
                "gtime": "18:30",
                "hCode": "HH",
                "hName": "Home",
                "hPCode": "1001",
                "aCode": "AW",
                "aName": "Away",
                "aPCode": "2001",
                "round": 1,
                "gameFlag": "0",
                "stadium": "Test",
                "isPostSeason": False,
                "cancelFlag": False,
                "statusCode": "1",
                "ptsFlag": "Y",
            },
            "home_starter": [{"playerCode": "1001", "playerName": "Pitcher", "position": "1", "positionName": "P", "birth": "19900101"}],
            "home_bullpen": [],
            "home_candidate": [],
            "away_starter": [{"playerCode": "2001", "playerName": "AwayPitcher", "position": "1", "positionName": "P"}],
            "away_bullpen": [],
            "away_candidate": [],
        },
        "relay": [
            [
                {
                    "title": "1회초",
                    "titleStyle": "0",
                    "no": 0,
                    "inn": 1,
                    "homeOrAway": "0",
                    "statusCode": 0,
                    "textOptions": [
                        {
                            "seqno": 1,
                            "type": 1,
                            "text": "event",
                            "currentGameState": {"pitcher": "1001", "batter": "2002", "out": 0, "ball": 0, "strike": 0, "base1": 0, "base2": 0, "base3": 0},
                            "currentPlayersInfo": {"unused": True},
                            "batterRecord": {"pcode": "2002", "name": "unused"},
                        }
                    ],
                    "ptsOptions": [{"pitchId": "p1", "inn": 1, "crossPlateX": 0.1}],
                    "metricOption": {"homeTeamWinRate": 0.5, "awayTeamWinRate": 0.5, "wpaByPlate": 0.1, "other": 9},
                }
            ]
        ],
        "record": {
            "batter": {
                "home": [],
                "away": [{"playerCode": "2002", "name": "B", "batOrder": 1, "ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0, "inn1": "K"}],
                "homeTotal": {},
                "awayTotal": {"ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0, "inn1": "K"},
            },
            "pitcher": {
                "home": [{"pcode": "1001", "name": "Pitcher", "inn": "1.0", "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "ab": 1, "bf": 1, "pa": 1, "bbhp": 0, "era": 0.0}],
                "away": [],
            },
        },
    }

    minimized = minimize_game_payload(raw_payload, file_path=Path("games/2026/20260406TEST.json"))

    assert minimized["schema_version"] == 2
    assert minimized["game_id"] == "20260406TEST"
    assert "currentPlayersInfo" not in minimized["relay"][0][0]["textOptions"][0]
    assert "birth" not in minimized["lineup"]["home_starter"][0]
    assert "inn1" not in minimized["record"]["batter"]["away"][0]
    assert "era" not in minimized["record"]["pitcher"]["home"][0]


@pytest.mark.parametrize(
    "source_path",
    [
        Path("example/20240724WOOB02024.json"),
        Path("example/20250409NCKT02025.json"),
    ],
)
def test_migrated_real_game_preserves_source_profile_counts(tmp_path: Path, source_path: Path):
    raw_payload = load_real_payload(source_path)
    migrated_payload = minimize_game_payload(raw_payload, file_path=source_path)

    migrated_path = tmp_path / source_path.name
    migrated_path.write_text(pretty_game_json(migrated_payload), encoding="utf-8")

    raw_profile = build_source_profile(source_path, project_root=Path.cwd())
    migrated_profile = build_source_profile(migrated_path, project_root=tmp_path)

    assert migrated_profile["expected_terminal_plate_appearances"] == raw_profile["expected_terminal_plate_appearances"]
    assert migrated_profile["expected_partial_plate_appearances"] == raw_profile["expected_partial_plate_appearances"]
    assert migrated_profile["expected_counts"]["plate_appearances"] == raw_profile["expected_counts"]["plate_appearances"]
    assert migrated_profile["expected_batter_totals"] == raw_profile["expected_batter_totals"]


@pytest.mark.parametrize(
    "source_path",
    [
        Path("example/20240724WOOB02024.json"),
        Path("example/20250311LGLT02025.json"),
    ],
)
def test_validate_game_accepts_minimized_real_payload(source_path: Path):
    raw_payload = load_real_payload(source_path)
    migrated_payload = minimize_game_payload(raw_payload, file_path=source_path)

    assert validate_game(migrated_payload) == validate_game(raw_payload)
