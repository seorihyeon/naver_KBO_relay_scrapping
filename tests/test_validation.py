from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.validation import _expected_pitch_tracking_gap, _is_source_derived_issue


def test_expected_pitch_tracking_gap_allows_games_without_pts_options():
    entry = {"expected_counts": {"pitches": 377, "pitch_tracking": 0}}

    assert _expected_pitch_tracking_gap(entry) == 377


def test_expected_pitch_tracking_gap_allows_partial_tracking_coverage():
    entry = {"expected_counts": {"pitches": 253, "pitch_tracking": 252}}

    assert _expected_pitch_tracking_gap(entry) == 1


def test_source_derived_issue_recognizes_pitcher_total_mismatch():
    issue = {
        "path": "games/2024/20240504OBLG02024.json",
        "code": "pitcher_total_mismatch:away:53259:pa",
        "message": "expected 20, got 19",
    }

    assert _is_source_derived_issue(issue, {"games/2024/20240504OBLG02024.json"})
