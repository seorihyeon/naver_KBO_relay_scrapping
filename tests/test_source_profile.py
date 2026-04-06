from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.source_profile import build_source_profile


def test_build_source_profile_counts_partial_plate_appearance_regression():
    json_path = Path("games/2025/20250831NCSK02025.json")

    profile = build_source_profile(json_path, project_root=Path.cwd())

    assert profile["expected_terminal_plate_appearances"] == 87
    assert profile["expected_partial_plate_appearances"] == 1
    assert profile["expected_counts"]["plate_appearances"] == 88


def test_build_source_profile_deduplicates_duplicate_terminal_events():
    json_path = Path("games/2024/20240724WOOB02024.json")

    profile = build_source_profile(json_path, project_root=Path.cwd())

    assert profile["expected_terminal_plate_appearances"] == 77
    assert profile["expected_partial_plate_appearances"] == 2
    assert profile["expected_counts"]["plate_appearances"] == 79
    assert profile["expected_batter_totals"]["away"]["pa"] == 38


def test_build_source_profile_uses_batter_credit_owner_rules():
    json_path = Path("games/2025/20250919LTNC02025.json")

    profile = build_source_profile(json_path, project_root=Path.cwd())
    home_rows = profile["expected_batter_totals_by_player"]["home"]

    assert home_rows["66606"]["ab"] == 2
    assert home_rows["66606"]["so"] == 1
    assert home_rows["67905"]["ab"] == 2
    assert home_rows["67905"]["so"] == 1


def test_build_source_profile_uses_pitcher_credit_owner_rules():
    json_path = Path("games/2024/20240407KTLG02024.json")

    profile = build_source_profile(json_path, project_root=Path.cwd())
    away_rows = profile["expected_pitcher_totals_by_player"]["away"]

    assert away_rows["69068"]["bb"] == 4
    assert away_rows["69068"]["bbhp"] == 4
    assert away_rows["66047"]["bb"] == 0
