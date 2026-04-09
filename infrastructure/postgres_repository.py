"""PostgreSQL adapters for game selection and replay dataset loading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from core.replay.models import (
    EventRow,
    GameContext,
    InningRow,
    PitchRow,
    PlayerInfo,
    PlateAppearanceRow,
    ReplayDataset,
    RosterEntryRow,
    SubstitutionRow,
)
from services.common import GameOption


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _parse_batting_side(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    text = str(raw_text)
    if "\uC591\uD0C0" in text:
        return "S"
    if "\uC88C\uD0C0" in text:
        return "L"
    if "\uC6B0\uD0C0" in text:
        return "R"
    return None


class PostgresConnectionFactory:
    """Creates autocommit PostgreSQL connections for service workflows."""

    def connect(self, dsn: str) -> psycopg.Connection:
        conn = psycopg.connect(dsn)
        conn.autocommit = True
        return conn


@dataclass
class GameCatalogRepository:
    """Reads selectable game metadata for GUI lookup controls."""

    conn: psycopg.Connection

    def list_games(self, *, limit: int = 500, search: str | None = None, offset: int = 0) -> list[GameOption]:
        where_sql = ""
        params: list[Any] = []
        if search:
            where_sql = """
            WHERE CAST(g.game_id AS text) ILIKE %s
               OR COALESCE(at.team_name_short, '') ILIKE %s
               OR COALESCE(ht.team_name_short, '') ILIKE %s
            """
            like = f"%{search}%"
            params.extend([like, like, like])
        params.extend([limit, offset])
        query = f"""
        SELECT g.game_id,
               COALESCE(to_char(g.game_date,'YYYY-MM-DD'),'NO_DATE') || ' | ' ||
               COALESCE(at.team_name_short,'AWAY') || ' vs ' || COALESCE(ht.team_name_short,'HOME') ||
               ' | game_id=' || g.game_id::text AS label
        FROM games g
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        {where_sql}
        ORDER BY g.game_date DESC NULLS LAST, g.game_id DESC
        LIMIT %s OFFSET %s
        """
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [GameOption(game_id=row[0], label=row[1]) for row in rows]


@dataclass
class ReplayRepository:
    """Loads replay datasets from PostgreSQL without any GUI dependency."""

    conn: psycopg.Connection
    _pa_event_columns: set[str] | None = None

    def get_pa_event_columns(self) -> set[str]:
        if self._pa_event_columns is None:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'pa_events'
                    """
                )
                self._pa_event_columns = {row[0] for row in cur.fetchall()}
        return self._pa_event_columns

    def load_game(self, game_id: int) -> ReplayDataset:
        return ReplayDataset(
            context=self.fetch_game_context(game_id),
            players=self.fetch_players(),
            roster_entries=self.fetch_roster_entries(game_id),
            substitutions=self.fetch_substitutions(game_id),
            events=self.fetch_events(game_id),
            pitches=self.fetch_pitches(game_id),
            plate_appearances=self.fetch_plate_appearances(game_id),
            innings=self.fetch_innings(game_id),
        )

    def fetch_players(self) -> list[PlayerInfo]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT player_id, player_name, height, bats_throws_text, hit_type_text FROM players")
            rows = cur.fetchall()
        players: list[PlayerInfo] = []
        for player_id, player_name, height, bats_throws_text, hit_type_text in rows:
            if not player_id:
                continue
            batting_side = _parse_batting_side(hit_type_text) or _parse_batting_side(bats_throws_text)
            players.append(
                PlayerInfo(
                    player_id=player_id,
                    player_name=player_name,
                    height_cm=_safe_int(height),
                    bats_throws_text=bats_throws_text,
                    hit_type_text=hit_type_text,
                    batting_side=batting_side,
                )
            )
        return players

    def fetch_game_context(self, game_id: int) -> GameContext:
        query = """
        SELECT g.game_id,
               g.game_date,
               g.home_team_id,
               g.away_team_id,
               ht.team_name_short,
               at.team_name_short
        FROM games g
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        WHERE g.game_id = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            row = cur.fetchone()
        if not row:
            raise LookupError(f"game_id={game_id} not found")
        return GameContext(
            game_id=row[0],
            game_date=row[1],
            home_team_id=row[2],
            away_team_id=row[3],
            home_team_name=row[4] or "HOME",
            away_team_name=row[5] or "AWAY",
        )

    def fetch_events(self, game_id: int) -> list[EventRow]:
        columns = self.get_pa_event_columns()
        b1_name_expr = "e.base1_runner_name" if "base1_runner_name" in columns else "NULL"
        b2_name_expr = "e.base2_runner_name" if "base2_runner_name" in columns else "NULL"
        b3_name_expr = "e.base3_runner_name" if "base3_runner_name" in columns else "NULL"
        b1_id_expr = "e.base1_runner_id" if "base1_runner_id" in columns else "NULL"
        b2_id_expr = "e.base2_runner_id" if "base2_runner_id" in columns else "NULL"
        b3_id_expr = "e.base3_runner_id" if "base3_runner_id" in columns else "NULL"
        query = f"""
        SELECT e.event_id, e.event_seq_game, i.inning_no, i.half, e.pa_id, e.event_seq_in_pa,
               e.event_category, e.text, e.outs, e.balls, e.strikes,
               e.base1_occupied, e.base2_occupied, e.base3_occupied,
               e.home_score, e.away_score,
               {b1_name_expr},
               {b2_name_expr},
               {b3_name_expr},
               {b1_id_expr},
               {b2_id_expr},
               {b3_id_expr}
        FROM pa_events e
        LEFT JOIN innings i ON i.inning_id = e.inning_id
        WHERE e.game_id = %s
        ORDER BY e.event_seq_game
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            EventRow(
                event_id=row[0],
                event_seq_game=_safe_int(row[1]),
                inning_no=_safe_int(row[2]),
                half=row[3],
                pa_id=row[4],
                event_seq_in_pa=_safe_int(row[5]),
                event_category=row[6],
                text=row[7],
                outs=_safe_int(row[8]),
                balls=_safe_int(row[9]),
                strikes=_safe_int(row[10]),
                base1_occupied=row[11],
                base2_occupied=row[12],
                base3_occupied=row[13],
                home_score=_safe_int(row[14]),
                away_score=_safe_int(row[15]),
                base1_runner_name=row[16],
                base2_runner_name=row[17],
                base3_runner_name=row[18],
                base1_runner_id=row[19],
                base2_runner_id=row[20],
                base3_runner_id=row[21],
            )
            for row in rows
        ]

    def fetch_pitches(self, game_id: int) -> list[PitchRow]:
        query = """
        SELECT p.pitch_id, p.event_id, p.pa_id, p.inning_id, p.pitch_num, p.pitch_result, p.pitch_type_text, p.speed_kph,
               p.balls_before, p.strikes_before, p.balls_after, p.strikes_after, p.is_in_play, p.is_terminal_pitch,
               pt.cross_plate_x, pt.cross_plate_y, pt.top_sz, pt.bottom_sz,
               pt.x0, pt.y0, pt.z0, pt.vx0, pt.vy0, pt.vz0, pt.ax, pt.ay, pt.az, pt.stance
        FROM pitches p
        LEFT JOIN pitch_tracking pt ON pt.pitch_id = p.pitch_id
        WHERE p.game_id = %s
        ORDER BY p.inning_id NULLS LAST, p.pa_id NULLS LAST, p.pitch_num NULLS LAST, p.pitch_id
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            PitchRow(
                pitch_id=row[0],
                event_id=row[1],
                pa_id=row[2],
                inning_id=row[3],
                pitch_num=_safe_int(row[4]),
                pitch_result=row[5],
                pitch_type_text=row[6],
                speed_kph=row[7],
                balls_before=_safe_int(row[8]),
                strikes_before=_safe_int(row[9]),
                balls_after=_safe_int(row[10]),
                strikes_after=_safe_int(row[11]),
                is_in_play=row[12],
                is_terminal_pitch=row[13],
                cross_plate_x=row[14],
                cross_plate_y=row[15],
                tracking_top=row[16],
                tracking_bottom=row[17],
                x0=row[18],
                y0=row[19],
                z0=row[20],
                vx0=row[21],
                vy0=row[22],
                vz0=row[23],
                ax=row[24],
                ay=row[25],
                az=row[26],
                stance=row[27],
            )
            for row in rows
        ]

    def fetch_plate_appearances(self, game_id: int) -> list[PlateAppearanceRow]:
        query = """
        SELECT pa.pa_id, pa.pa_seq_game, i.inning_no, i.half, pa.batter_id, pa.pitcher_id,
               pa.outs_before, pa.outs_after, pa.balls_final, pa.strikes_final,
               pa.result_text, pa.runs_scored_on_pa, pa.start_seqno, pa.end_seqno
        FROM plate_appearances pa
        LEFT JOIN innings i ON i.inning_id = pa.inning_id
        WHERE pa.game_id = %s
        ORDER BY pa.pa_seq_game
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            PlateAppearanceRow(
                pa_id=row[0],
                pa_seq_game=_safe_int(row[1]),
                inning_no=_safe_int(row[2]),
                half=row[3],
                batter_id=row[4],
                pitcher_id=row[5],
                outs_before=_safe_int(row[6]),
                outs_after=_safe_int(row[7]),
                balls_final=_safe_int(row[8]),
                strikes_final=_safe_int(row[9]),
                result_text=row[10],
                runs_scored_on_pa=_safe_int(row[11]),
                start_seqno=_safe_int(row[12]),
                end_seqno=_safe_int(row[13]),
            )
            for row in rows
        ]

    def fetch_innings(self, game_id: int) -> list[InningRow]:
        query = """
        SELECT inning_id, inning_no, half, batting_team_id, fielding_team_id,
               runs_scored, hits_in_half, errors_in_half, walks_in_half,
               start_event_seqno, end_event_seqno
        FROM innings
        WHERE game_id = %s
        ORDER BY inning_no, CASE WHEN half='top' THEN 0 ELSE 1 END
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            InningRow(
                inning_id=row[0],
                inning_no=_safe_int(row[1]),
                half=row[2],
                batting_team_id=row[3],
                fielding_team_id=row[4],
                runs_scored=_safe_int(row[5]),
                hits_in_half=_safe_int(row[6]),
                errors_in_half=_safe_int(row[7]),
                walks_in_half=_safe_int(row[8]),
                start_event_seqno=_safe_int(row[9]),
                end_event_seqno=_safe_int(row[10]),
            )
            for row in rows
        ]

    def fetch_roster_entries(self, game_id: int) -> list[RosterEntryRow]:
        query = """
        SELECT gre.team_id, gre.player_id, p.player_name, gre.roster_group,
               gre.is_starting_pitcher, gre.field_position_code, gre.field_position_name
        FROM game_roster_entries gre
        LEFT JOIN players p ON p.player_id = gre.player_id
        WHERE gre.game_id = %s
        ORDER BY gre.team_id, gre.is_starting_pitcher DESC, gre.roster_group, gre.game_roster_entry_id
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            RosterEntryRow(
                team_id=row[0],
                player_id=row[1],
                player_name=row[2],
                roster_group=row[3],
                is_starting_pitcher=row[4],
                field_position_code=row[5],
                field_position_name=row[6],
            )
            for row in rows
        ]

    def fetch_substitutions(self, game_id: int) -> list[SubstitutionRow]:
        query = """
        SELECT s.sub_event_id,
               s.event_id,
               e.event_seq_game,
               s.team_id,
               COALESCE(s.in_player_name, pin.player_name),
               COALESCE(s.out_player_name, pout.player_name),
               s.in_position,
               s.out_position,
               s.description
        FROM substitution_events s
        LEFT JOIN pa_events e ON e.event_id = s.event_id
        LEFT JOIN players pin ON pin.player_id = s.in_player_id
        LEFT JOIN players pout ON pout.player_id = s.out_player_id
        WHERE s.game_id = %s
        ORDER BY e.event_seq_game, s.sub_event_id
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            rows = cur.fetchall()
        return [
            SubstitutionRow(
                sub_event_id=row[0],
                event_id=row[1],
                event_seq_game=_safe_int(row[2]),
                team_id=row[3],
                in_player_name=row[4],
                out_player_name=row[5],
                in_position=row[6],
                out_position=row[7],
                description=row[8],
            )
            for row in rows
        ]
