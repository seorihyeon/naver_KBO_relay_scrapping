from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.replay import ReplayAnomalyDetector, ReplayNavigationModelBuilder, ReplayStateBuilder, StrikeZoneRuleBook
from core.replay.models import (
    EventRow,
    GameContext,
    InningRow,
    PitchRow,
    PlateAppearanceRow,
    PlayerInfo,
    ReplayDataset,
    RosterEntryRow,
)
from core.replay.roster import build_roster_context
from gui.state import AppState


def make_dataset() -> ReplayDataset:
    return ReplayDataset(
        context=GameContext(
            game_id=1,
            game_date=None,
            home_team_id=10,
            away_team_id=20,
            home_team_name="Home",
            away_team_name="Away",
        ),
        players=[
            PlayerInfo(player_id="HP", player_name="Home Pitcher", height_cm=188, bats_throws_text="우투우타", hit_type_text=None, batting_side="R"),
            PlayerInfo(player_id="B1", player_name="Kim", height_cm=180, bats_throws_text="우투좌타", hit_type_text=None, batting_side="L"),
        ],
        roster_entries=[
            RosterEntryRow(team_id=10, player_id="HP", player_name="Home Pitcher", roster_group="starter", is_starting_pitcher=True, field_position_code="1", field_position_name="투수"),
        ],
        substitutions=[],
        events=[
            EventRow(
                event_id=1,
                event_seq_game=1,
                inning_no=1,
                half="top",
                pa_id=101,
                event_seq_in_pa=1,
                event_category="other",
                text="1번타자 Kim",
                outs=0,
                balls=0,
                strikes=0,
                base1_occupied=False,
                base2_occupied=False,
                base3_occupied=False,
                home_score=0,
                away_score=0,
                base1_runner_name=None,
                base2_runner_name=None,
                base3_runner_name=None,
                base1_runner_id=None,
                base2_runner_id=None,
                base3_runner_id=None,
            ),
            EventRow(
                event_id=2,
                event_seq_game=2,
                inning_no=1,
                half="top",
                pa_id=101,
                event_seq_in_pa=2,
                event_category="bat_result",
                text="Kim : 좌전 1루타",
                outs=0,
                balls=0,
                strikes=0,
                base1_occupied=True,
                base2_occupied=False,
                base3_occupied=False,
                home_score=0,
                away_score=0,
                base1_runner_name=None,
                base2_runner_name=None,
                base3_runner_name=None,
                base1_runner_id=None,
                base2_runner_id=None,
                base3_runner_id=None,
            ),
        ],
        pitches=[
            PitchRow(
                pitch_id=201,
                event_id=2,
                pa_id=101,
                inning_id=301,
                pitch_num=1,
                pitch_result="X",
                pitch_type_text="FF",
                speed_kph=145.0,
                balls_before=0,
                strikes_before=0,
                balls_after=0,
                strikes_after=0,
                is_in_play=True,
                is_terminal_pitch=True,
                cross_plate_x=0.1,
                cross_plate_y=1.4,
                tracking_top=3.5,
                tracking_bottom=1.6,
                x0=0.0,
                y0=50.0,
                z0=6.0,
                vx0=0.0,
                vy0=-130.0,
                vz0=-5.0,
                ax=0.0,
                ay=32.0,
                az=-24.0,
                stance="L",
            )
        ],
        plate_appearances=[
            PlateAppearanceRow(
                pa_id=101,
                pa_seq_game=1,
                inning_no=1,
                half="top",
                batter_id="B1",
                pitcher_id="HP",
                outs_before=0,
                outs_after=0,
                balls_final=0,
                strikes_final=0,
                result_text="Kim : 좌전 1루타",
                runs_scored_on_pa=0,
                start_seqno=1,
                end_seqno=2,
            )
        ],
        innings=[
            InningRow(
                inning_id=301,
                inning_no=1,
                half="top",
                batting_team_id=20,
                fielding_team_id=10,
                runs_scored=0,
                hits_in_half=1,
                errors_in_half=0,
                walks_in_half=0,
                start_event_seqno=1,
                end_event_seqno=2,
            )
        ],
    )


def test_replay_state_builder_resolves_runner_and_pitch_context():
    dataset = make_dataset()
    state = AppState(config={})
    roster_context = build_roster_context(dataset)
    builder = ReplayStateBuilder(dataset, roster_context, StrikeZoneRuleBook(dict(state.strike_zone_rules)))

    resolved = builder.get_resolved_game_state(1)
    pitch_context = builder.current_pitch_tracking(dataset.pitches[0])

    assert resolved.b1_occ is True
    assert resolved.b1_name == "Kim"
    assert pitch_context is not None
    assert pitch_context.rule_year in {2024, 2025}
    assert pitch_context.zone_half_width is not None


def test_replay_navigation_builder_creates_focus_models():
    dataset = make_dataset()
    state = AppState(config={})
    roster_context = build_roster_context(dataset)
    builder = ReplayStateBuilder(dataset, roster_context, StrikeZoneRuleBook(dict(state.strike_zone_rules)))

    navigation = ReplayNavigationModelBuilder(builder).build()

    assert len(navigation.pitch_items) == 1
    assert len(navigation.pa_items) == 1
    assert len(navigation.inning_items) == 1
    assert navigation.event_index_by_id[2] == 1
    assert navigation.pa_index_by_id[101] == 0


def test_replay_anomaly_detector_flags_regressions():
    warnings = ReplayAnomalyDetector().detect(
        [
            EventRow(1, 1, 1, "top", 101, 1, "other", "text", 0, 2, 2, False, False, False, 1, 0, None, None, None, None, None, None),
            EventRow(2, 2, 1, "top", 101, 2, "other", "text", 0, 1, 1, False, False, False, 0, 0, None, None, None, None, None, None),
        ]
    )

    codes = {warning.code for warning in warnings}
    assert "balls_regressed" in codes
    assert "strikes_regressed" in codes
    assert "home_score_regressed" in codes
