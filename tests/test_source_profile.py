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
