from pathlib import Path
import sys
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from web_interface import Scrapper


def test_normalize_game_url_with_relative_path():
    assert (
        Scrapper.normalize_game_url("/game/20260403SSKT02026")
        == "https://m.sports.naver.com/game/20260403SSKT02026"
    )


def test_normalize_game_url_with_absolute_url():
    url = "https://m.sports.naver.com/game/20250409NCKT02025"
    assert Scrapper.normalize_game_url(url) == url


def test_extract_game_id_from_nested_game_url():
    assert (
        Scrapper.extract_game_id("https://m.sports.naver.com/game/20250409NCKT02025/relay")
        == "20250409NCKT02025"
    )


def test_get_inning_count_from_relay_summary():
    relay_summary = {
        "result": {
            "textRelayData": {
                "inningScore": {
                    "home": {"1": "0", "2": "1", "10": "-"},
                    "away": {"1": "2", "2": "0", "10": "0"},
                }
            }
        }
    }

    scraper = Scrapper.__new__(Scrapper)
    assert scraper.get_inning_count(relay_summary) == 10


def test_throttle_api_request_waits_for_remaining_interval():
    scraper = Scrapper.__new__(Scrapper)
    scraper.api_request_interval = 0.25
    scraper._last_api_request_finished_at = 10.0

    with patch("web_interface.time.monotonic", return_value=10.1), patch("web_interface.time.sleep") as sleep_mock:
        scraper._throttle_api_request()

    sleep_mock.assert_called_once()
    assert abs(sleep_mock.call_args.args[0] - 0.15) < 1e-9


def test_throttle_api_request_skips_sleep_when_interval_elapsed():
    scraper = Scrapper.__new__(Scrapper)
    scraper.api_request_interval = 0.25
    scraper._last_api_request_finished_at = 10.0

    with patch("web_interface.time.monotonic", return_value=10.4), patch("web_interface.time.sleep") as sleep_mock:
        scraper._throttle_api_request()

    sleep_mock.assert_not_called()
