import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Json

from common_utils import first_non_empty, to_int


def _extract_game_meta(lineup: dict[str, Any]) -> dict[str, Any]:
    info = lineup.get("game_info") or {}
    raw_date = first_non_empty(info.get("gdate"), info.get("gameDate"), info.get("date"))
    parsed_date = None
    if raw_date:
        try:
            parsed_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            parsed_date = None
    return {
        "game_date": parsed_date,
        "stadium": first_non_empty(info.get("stadium"), info.get("stadiumName")),
        "home_team_code": first_non_empty(info.get("hCode"), info.get("homeTeamCode"), info.get("hcode")),
        "away_team_code": first_non_empty(info.get("aCode"), info.get("awayTeamCode"), info.get("acode")),
        "home_team_name": first_non_empty(info.get("hName"), info.get("homeTeamName"), info.get("hFullName")),
        "away_team_name": first_non_empty(info.get("aName"), info.get("awayTeamName"), info.get("aFullName")),
    }


def _iter_players(game: dict[str, Any]) -> Iterable[dict[str, Any]]:
    lineup = game.get("lineup") or {}
    record = game.get("record") or {}

    for side in ("home", "away"):
        for section in ("starter", "bullpen", "candidate"):
            for row in lineup.get(f"{side}_{section}") or []:
                player_id = str(first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")) or "")
                if not player_id:
                    continue
                yield {
                    "player_id": player_id,
                    "name": first_non_empty(row.get("playerName"), row.get("name"), "UNKNOWN"),
                    "throws": first_non_empty(row.get("throwBat"), row.get("throws")),
                    "bats": first_non_empty(row.get("hitType"), row.get("bats")),
                    "raw": row,
                }

    for section, key in (("batter", "playerCode"), ("pitcher", "pcode")):
        boxscore = record.get(section) or {}
        for side in ("home", "away"):
            for row in boxscore.get(side) or []:
                player_id = str(first_non_empty(row.get(key), row.get("playerCode"), row.get("pcode")) or "")
                if not player_id:
                    continue
                yield {
                    "player_id": player_id,
                    "name": first_non_empty(row.get("name"), row.get("playerName"), "UNKNOWN"),
                    "throws": first_non_empty(row.get("hitType"), row.get("throws")),
                    "bats": first_non_empty(row.get("hitType"), row.get("bats")),
                    "raw": row,
                }


def _map_event_type(type_code: Any, text: str) -> tuple[str, str | None]:
    code = to_int(type_code, -1)
    txt = text or ""

    if code in (1, 2, 3):
        return "SYSTEM", f"system_{code}"
    if code in (7, 8, 9):
        return "PITCH", f"pitch_{code}"
    if code in (13, 23):
        return "PLATE_APPEARANCE", "pa_result"
    if "견제" in txt:
        return "PICKOFF_ATTEMPT", None
    if "도루" in txt:
        return "RUNNER_ADVANCE", "stolen_base"
    if "비디오" in txt or "판독" in txt:
        return "REVIEW", None
    if "마운드 방문" in txt:
        return "MOUND_VISIT", None
    if "교체" in txt:
        return "SUBSTITUTION", None
    return "MISC", f"type_{code}"


@dataclass
class EventRow:
    seq_no: int
    inning: int | None
    half: str | None
    event_type: str
    event_subtype: str | None
    text: str
    raw: dict[str, Any]
    batter_id: str | None
    pitcher_id: str | None
    outs_before: int | None
    balls_before: int | None
    strikes_before: int | None
    score_home_before: int | None
    score_away_before: int | None


def _extract_events(relay: list[Any]) -> list[EventRow]:
    rows: list[EventRow] = []
    seq_no = 1

    for inning_idx, inning_block in enumerate(relay, start=1):
        for half_block in inning_block or []:
            home_or_away = str(half_block.get("homeOrAway", ""))
            half = "T" if home_or_away == "0" else "B"
            inning_no = to_int(first_non_empty(half_block.get("inning"), half_block.get("inn")), inning_idx)

            for item in half_block.get("textOptions") or []:
                state = item.get("currentGameState") or {}
                text = item.get("text") or ""
                event_type, subtype = _map_event_type(item.get("type"), text)

                rows.append(
                    EventRow(
                        seq_no=seq_no,
                        inning=inning_no,
                        half=half,
                        event_type=event_type,
                        event_subtype=subtype,
                        text=text,
                        raw=item,
                        batter_id=str(state.get("batter")) if state.get("batter") else None,
                        pitcher_id=str(state.get("pitcher")) if state.get("pitcher") else None,
                        outs_before=to_int(first_non_empty(state.get("outCount"), state.get("outs")), None),
                        balls_before=to_int(first_non_empty(state.get("ballCount"), state.get("balls")), None),
                        strikes_before=to_int(first_non_empty(state.get("strikeCount"), state.get("strikes")), None),
                        score_home_before=to_int(
                            first_non_empty(state.get("homeTeamScore"), state.get("homeScore")), None
                        ),
                        score_away_before=to_int(
                            first_non_empty(state.get("awayTeamScore"), state.get("awayScore")), None
                        ),
                    )
                )
                seq_no += 1
    return rows


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    team_code TEXT PRIMARY KEY,
    team_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    player_name TEXT NOT NULL,
    throws TEXT,
    bats TEXT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    game_date DATE,
    stadium TEXT,
    home_team_code TEXT REFERENCES teams(team_code),
    away_team_code TEXT REFERENCES teams(team_code),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_games (
    game_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    payload JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    event_id BIGSERIAL PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    seq_no INTEGER NOT NULL,
    prev_event_id BIGINT REFERENCES events(event_id),
    next_event_id BIGINT REFERENCES events(event_id),
    inning INTEGER,
    half CHAR(1),
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    description TEXT,
    batter_id TEXT REFERENCES players(player_id),
    pitcher_id TEXT REFERENCES players(player_id),
    outs_before SMALLINT,
    balls_before SMALLINT,
    strikes_before SMALLINT,
    score_home_before SMALLINT,
    score_away_before SMALLINT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (game_id, seq_no)
);

CREATE TABLE IF NOT EXISTS event_links (
    from_event_id BIGINT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    to_event_id BIGINT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (from_event_id, to_event_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_events_game_seq ON events (game_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type, event_subtype);
"""


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def upsert_game_bundle(conn: psycopg.Connection, game_id: str, source_path: Path, payload: dict[str, Any]) -> None:
    lineup = payload.get("lineup") or {}
    meta = _extract_game_meta(lineup)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_games (game_id, source_path, payload)
            VALUES (%s, %s, %s)
            ON CONFLICT (game_id)
            DO UPDATE SET source_path = EXCLUDED.source_path,
                          payload = EXCLUDED.payload,
                          ingested_at = NOW()
            """,
            (game_id, str(source_path), Json(payload)),
        )

        for team_code, team_name in (
            (meta["home_team_code"], meta["home_team_name"]),
            (meta["away_team_code"], meta["away_team_name"]),
        ):
            if not team_code:
                continue
            cur.execute(
                """
                INSERT INTO teams (team_code, team_name)
                VALUES (%s, %s)
                ON CONFLICT (team_code)
                DO UPDATE SET team_name = COALESCE(EXCLUDED.team_name, teams.team_name),
                              updated_at = NOW()
                """,
                (str(team_code), team_name),
            )

        for player in _iter_players(payload):
            cur.execute(
                """
                INSERT INTO players (player_id, player_name, throws, bats, raw_payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (player_id)
                DO UPDATE SET player_name = COALESCE(EXCLUDED.player_name, players.player_name),
                              throws = COALESCE(EXCLUDED.throws, players.throws),
                              bats = COALESCE(EXCLUDED.bats, players.bats),
                              raw_payload = EXCLUDED.raw_payload,
                              updated_at = NOW()
                """,
                (
                    player["player_id"],
                    player["name"],
                    player["throws"],
                    player["bats"],
                    Json(player["raw"]),
                ),
            )

        cur.execute(
            """
            INSERT INTO games (game_id, game_date, stadium, home_team_code, away_team_code, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id)
            DO UPDATE SET game_date = COALESCE(EXCLUDED.game_date, games.game_date),
                          stadium = COALESCE(EXCLUDED.stadium, games.stadium),
                          home_team_code = COALESCE(EXCLUDED.home_team_code, games.home_team_code),
                          away_team_code = COALESCE(EXCLUDED.away_team_code, games.away_team_code),
                          raw_payload = EXCLUDED.raw_payload,
                          updated_at = NOW()
            """,
            (
                game_id,
                meta["game_date"],
                meta["stadium"],
                str(meta["home_team_code"]) if meta["home_team_code"] else None,
                str(meta["away_team_code"]) if meta["away_team_code"] else None,
                Json(meta),
            ),
        )

        cur.execute(
            """
            DELETE FROM event_links
            WHERE from_event_id IN (SELECT event_id FROM events WHERE game_id = %s)
               OR to_event_id IN (SELECT event_id FROM events WHERE game_id = %s)
            """,
            (game_id, game_id),
        )
        cur.execute("DELETE FROM events WHERE game_id = %s", (game_id,))

        relay = payload.get("relay") or []
        prev_event_id: int | None = None
        for row in _extract_events(relay):
            cur.execute(
                """
                INSERT INTO events (
                    game_id, seq_no, prev_event_id, inning, half,
                    event_type, event_subtype, description,
                    batter_id, pitcher_id,
                    outs_before, balls_before, strikes_before,
                    score_home_before, score_away_before,
                    raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING event_id
                """,
                (
                    game_id,
                    row.seq_no,
                    prev_event_id,
                    row.inning,
                    row.half,
                    row.event_type,
                    row.event_subtype,
                    row.text,
                    row.batter_id,
                    row.pitcher_id,
                    row.outs_before,
                    row.balls_before,
                    row.strikes_before,
                    row.score_home_before,
                    row.score_away_before,
                    Json(row.raw),
                ),
            )
            current_event_id = cur.fetchone()[0]
            if prev_event_id is not None:
                cur.execute("UPDATE events SET next_event_id = %s WHERE event_id = %s", (current_event_id, prev_event_id))
                cur.execute(
                    "INSERT INTO event_links (from_event_id, to_event_id, link_type) VALUES (%s, %s, 'NEXT')",
                    (prev_event_id, current_event_id),
                )
            prev_event_id = current_event_id

    conn.commit()


def iter_json_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Naver KBO JSON -> PostgreSQL 적재기")
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN (예: postgresql://user:pass@localhost:5432/kbo)")
    parser.add_argument("--data-dir", default="games", help="스크래핑 JSON이 저장된 루트 디렉터리")
    parser.add_argument("--create-schema", action="store_true", help="적재 전에 테이블 DDL 생성")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"data-dir not found: {data_dir}")

    with psycopg.connect(args.dsn) as conn:
        if args.create_schema:
            create_schema(conn)

        total = 0
        for json_path in iter_json_files(data_dir):
            with json_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            game_id = json_path.stem
            upsert_game_bundle(conn, game_id, json_path, payload)
            total += 1
            print(f"[OK] loaded {json_path}")

    print(f"done. loaded games={total}")


if __name__ == "__main__":
    main()
