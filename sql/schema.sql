CREATE TABLE IF NOT EXISTS teams (
    team_id BIGSERIAL PRIMARY KEY,
    team_code TEXT NOT NULL UNIQUE,
    team_name_short TEXT,
    team_name_full TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    player_name TEXT,
    birth_date DATE,
    bats_throws_text TEXT,
    hit_type_text TEXT,
    height INTEGER,
    weight INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stadiums (
    stadium_id BIGSERIAL PRIMARY KEY,
    stadium_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_games (
    raw_game_id BIGSERIAL PRIMARY KEY,
    source_file_name TEXT NOT NULL,
    source_file_hash TEXT NOT NULL UNIQUE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_relay_blocks (
    raw_block_id BIGSERIAL PRIMARY KEY,
    raw_game_id BIGINT NOT NULL REFERENCES raw_games(raw_game_id) ON DELETE CASCADE,
    block_index INTEGER NOT NULL,
    title TEXT,
    title_style TEXT,
    block_no INTEGER,
    inning_no INTEGER,
    home_or_away TEXT,
    status_code TEXT,
    raw_block_json JSONB NOT NULL,
    UNIQUE(raw_game_id, block_index)
);

CREATE TABLE IF NOT EXISTS raw_text_events (
    raw_event_id BIGSERIAL PRIMARY KEY,
    raw_block_id BIGINT NOT NULL REFERENCES raw_relay_blocks(raw_block_id) ON DELETE CASCADE,
    event_index_in_block INTEGER NOT NULL,
    seqno INTEGER,
    type_code INTEGER,
    text TEXT,
    current_game_state_json JSONB,
    batter_record_json JSONB,
    current_players_info_json JSONB,
    player_change_json JSONB,
    pitch_num INTEGER,
    pitch_result TEXT,
    pts_pitch_id TEXT,
    speed_kph DOUBLE PRECISION,
    stuff_text TEXT,
    raw_event_json JSONB NOT NULL,
    UNIQUE(raw_block_id, event_index_in_block)
);

CREATE TABLE IF NOT EXISTS raw_pitch_tracks (
    raw_pitch_track_id BIGSERIAL PRIMARY KEY,
    raw_block_id BIGINT NOT NULL REFERENCES raw_relay_blocks(raw_block_id) ON DELETE CASCADE,
    pitch_id TEXT,
    inn INTEGER,
    ballcount TEXT,
    cross_plate_x DOUBLE PRECISION,
    cross_plate_y DOUBLE PRECISION,
    top_sz DOUBLE PRECISION,
    bottom_sz DOUBLE PRECISION,
    vx0 DOUBLE PRECISION,
    vy0 DOUBLE PRECISION,
    vz0 DOUBLE PRECISION,
    ax DOUBLE PRECISION,
    ay DOUBLE PRECISION,
    az DOUBLE PRECISION,
    x0 DOUBLE PRECISION,
    y0 DOUBLE PRECISION,
    z0 DOUBLE PRECISION,
    stance TEXT,
    raw_track_json JSONB NOT NULL,
    UNIQUE(raw_block_id, pitch_id)
);

CREATE TABLE IF NOT EXISTS raw_plate_metrics (
    raw_block_id BIGINT PRIMARY KEY REFERENCES raw_relay_blocks(raw_block_id) ON DELETE CASCADE,
    home_team_win_rate DOUBLE PRECISION,
    away_team_win_rate DOUBLE PRECISION,
    wpa_by_plate DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS games (
    game_id BIGSERIAL PRIMARY KEY,
    raw_game_id BIGINT NOT NULL UNIQUE REFERENCES raw_games(raw_game_id) ON DELETE CASCADE,
    source_game_key TEXT NOT NULL UNIQUE,
    game_date DATE,
    game_time TEXT,
    stadium_id BIGINT REFERENCES stadiums(stadium_id),
    home_team_id BIGINT REFERENCES teams(team_id),
    away_team_id BIGINT REFERENCES teams(team_id),
    round_no TEXT,
    game_flag TEXT,
    is_postseason BOOLEAN,
    cancel_flag BOOLEAN,
    status_code TEXT,
    source_file_name TEXT
);

CREATE TABLE IF NOT EXISTS game_roster_entries (
    game_roster_entry_id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    team_id BIGINT REFERENCES teams(team_id),
    player_id TEXT REFERENCES players(player_id),
    roster_group TEXT NOT NULL,
    is_starting_pitcher BOOLEAN,
    batting_order_slot INTEGER,
    field_position_code TEXT,
    field_position_name TEXT,
    back_number TEXT
);

CREATE TABLE IF NOT EXISTS innings (
    inning_id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_no INTEGER NOT NULL,
    half TEXT NOT NULL,
    batting_team_id BIGINT REFERENCES teams(team_id),
    fielding_team_id BIGINT REFERENCES teams(team_id),
    start_event_seqno INTEGER,
    end_event_seqno INTEGER,
    runs_scored INTEGER,
    hits_in_half INTEGER,
    errors_in_half INTEGER,
    walks_in_half INTEGER,
    UNIQUE(game_id, inning_no, half)
);

CREATE TABLE IF NOT EXISTS plate_appearances (
    pa_id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_seq_game INTEGER NOT NULL,
    pa_seq_in_half INTEGER,
    batter_id TEXT REFERENCES players(player_id),
    pitcher_id TEXT REFERENCES players(player_id),
    batting_order_slot INTEGER,
    outs_before INTEGER,
    outs_after INTEGER,
    balls_final INTEGER,
    strikes_final INTEGER,
    bases_before TEXT,
    bases_after TEXT,
    result_code TEXT,
    result_text TEXT,
    is_terminal BOOLEAN,
    rbi INTEGER,
    runs_scored_on_pa INTEGER,
    start_seqno INTEGER,
    end_seqno INTEGER,
    start_pitch_num INTEGER,
    end_pitch_num INTEGER,
    raw_block_id BIGINT REFERENCES raw_relay_blocks(raw_block_id),
    wpa_by_plate DOUBLE PRECISION,
    home_win_rate_after DOUBLE PRECISION,
    away_win_rate_after DOUBLE PRECISION,
    UNIQUE(game_id, pa_seq_game)
);

CREATE TABLE IF NOT EXISTS pa_events (
    event_id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    event_seq_game INTEGER NOT NULL,
    event_seq_in_pa INTEGER,
    event_type_code INTEGER,
    event_category TEXT NOT NULL,
    text TEXT,
    batter_id TEXT,
    pitcher_id TEXT,
    outs INTEGER,
    balls INTEGER,
    strikes INTEGER,
    base1_occupied BOOLEAN,
    base2_occupied BOOLEAN,
    base3_occupied BOOLEAN,
    home_score INTEGER,
    away_score INTEGER,
    home_hits INTEGER,
    away_hits INTEGER,
    home_errors INTEGER,
    away_errors INTEGER,
    raw_event_id BIGINT REFERENCES raw_text_events(raw_event_id),
    raw_payload JSONB,
    UNIQUE(game_id, event_seq_game)
);

CREATE TABLE IF NOT EXISTS pitches (
    pitch_id TEXT PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    event_id BIGINT REFERENCES pa_events(event_id),
    pitch_num INTEGER,
    pitch_result TEXT,
    pitch_type_text TEXT,
    speed_kph DOUBLE PRECISION,
    balls_before INTEGER,
    strikes_before INTEGER,
    balls_after INTEGER,
    strikes_after INTEGER,
    is_in_play BOOLEAN,
    is_terminal_pitch BOOLEAN
);

CREATE TABLE IF NOT EXISTS pitch_tracking (
    pitch_id TEXT PRIMARY KEY REFERENCES pitches(pitch_id) ON DELETE CASCADE,
    ballcount TEXT,
    cross_plate_x DOUBLE PRECISION,
    cross_plate_y DOUBLE PRECISION,
    top_sz DOUBLE PRECISION,
    bottom_sz DOUBLE PRECISION,
    vx0 DOUBLE PRECISION,
    vy0 DOUBLE PRECISION,
    vz0 DOUBLE PRECISION,
    ax DOUBLE PRECISION,
    ay DOUBLE PRECISION,
    az DOUBLE PRECISION,
    x0 DOUBLE PRECISION,
    y0 DOUBLE PRECISION,
    z0 DOUBLE PRECISION,
    stance TEXT
);

CREATE TABLE IF NOT EXISTS batted_ball_results (
    batted_ball_result_id BIGSERIAL PRIMARY KEY,
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    event_id BIGINT REFERENCES pa_events(event_id),
    pitch_id TEXT REFERENCES pitches(pitch_id),
    result_code TEXT,
    result_text TEXT,
    hit_flag BOOLEAN,
    out_flag BOOLEAN,
    rbi INTEGER,
    fielding_sequence_text TEXT,
    error_flag BOOLEAN,
    sacrifice_flag BOOLEAN
);

CREATE TABLE IF NOT EXISTS baserunning_events (
    baserunning_event_id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    event_id BIGINT REFERENCES pa_events(event_id),
    runner_player_id TEXT REFERENCES players(player_id),
    runner_name_raw TEXT,
    start_base TEXT,
    end_base TEXT,
    event_subtype TEXT,
    is_out BOOLEAN,
    outs_recorded INTEGER,
    caused_by_error BOOLEAN,
    related_fielder_sequence TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS review_events (
    review_event_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES pa_events(event_id) ON DELETE CASCADE,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    request_team_id BIGINT REFERENCES teams(team_id),
    subject_type TEXT,
    original_call TEXT,
    final_call TEXT,
    review_target_text TEXT,
    started_at_text TEXT,
    ended_at_text TEXT,
    duration_seconds INTEGER,
    description TEXT
);

CREATE TABLE IF NOT EXISTS substitution_events (
    sub_event_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES pa_events(event_id) ON DELETE CASCADE,
    game_id BIGINT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    inning_id BIGINT REFERENCES innings(inning_id),
    pa_id BIGINT REFERENCES plate_appearances(pa_id),
    team_id BIGINT REFERENCES teams(team_id),
    sub_type TEXT,
    in_player_id TEXT REFERENCES players(player_id),
    out_player_id TEXT REFERENCES players(player_id),
    in_player_name TEXT,
    out_player_name TEXT,
    in_position TEXT,
    out_position TEXT,
    out_player_turn TEXT,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_blocks_game ON raw_relay_blocks(raw_game_id, block_index);
CREATE INDEX IF NOT EXISTS idx_raw_events_block_seq ON raw_text_events(raw_block_id, seqno);
CREATE INDEX IF NOT EXISTS idx_raw_pitch_tracks_pitch_id ON raw_pitch_tracks(pitch_id);
CREATE INDEX IF NOT EXISTS idx_roster_game_team ON game_roster_entries(game_id, team_id);
CREATE INDEX IF NOT EXISTS idx_pa_game_inning ON plate_appearances(game_id, inning_id);
CREATE INDEX IF NOT EXISTS idx_events_game_pa ON pa_events(game_id, pa_id);
CREATE INDEX IF NOT EXISTS idx_pitches_game_pa ON pitches(game_id, pa_id, pitch_num);
CREATE INDEX IF NOT EXISTS idx_baserunning_game_event ON baserunning_events(game_id, event_id);
