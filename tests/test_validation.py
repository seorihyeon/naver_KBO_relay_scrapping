from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.validation import _expected_pitch_tracking_gap


def test_expected_pitch_tracking_gap_allows_games_without_pts_options():
    entry = {"expected_counts": {"pitches": 377, "pitch_tracking": 0}}

    assert _expected_pitch_tracking_gap(entry) == 377


def test_expected_pitch_tracking_gap_allows_partial_tracking_coverage():
    entry = {"expected_counts": {"pitches": 253, "pitch_tracking": 252}}

    assert _expected_pitch_tracking_gap(entry) == 1
