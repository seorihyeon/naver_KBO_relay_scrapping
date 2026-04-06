from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.ingest_raw import _parse_game_date, _to_bool_flag


def test_to_bool_flag_handles_game_info_markers():
    assert _to_bool_flag(True) is True
    assert _to_bool_flag(False) is False
    assert _to_bool_flag("Y") is True
    assert _to_bool_flag("N") is False
    assert _to_bool_flag("1") is True
    assert _to_bool_flag("0") is False
    assert _to_bool_flag(None, default=True) is True


def test_parse_game_date_accepts_common_source_formats():
    assert str(_parse_game_date(20250308)) == "2025-03-08"
    assert str(_parse_game_date("2025-03-08")) == "2025-03-08"
    assert str(_parse_game_date("2025/03/08")) == "2025-03-08"
    assert _parse_game_date("") is None
