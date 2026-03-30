import argparse
from pathlib import Path

import psycopg

from src.kbo_ingest.pipeline import load_one_game, validate_game


def create_schema(conn: psycopg.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def iter_json_files(root: Path):
    yield from root.rglob("*.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="KBO JSON -> PostgreSQL 적재기 (raw + normalized)")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--data-dir", default="games")
    parser.add_argument("--schema", default="sql/schema.sql")
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"data-dir not found: {data_dir}")

    with psycopg.connect(args.dsn) as conn:
        if args.create_schema:
            create_schema(conn, Path(args.schema))

        total = 0
        for json_path in iter_json_files(data_dir):
            raw_game_id, game_id = load_one_game(conn, json_path)
            total += 1
            if args.validate:
                metrics = validate_game(conn, game_id)
                print(f"[OK] loaded {json_path} raw_game_id={raw_game_id} game_id={game_id} metrics={metrics}")
            else:
                print(f"[OK] loaded {json_path} raw_game_id={raw_game_id} game_id={game_id}")

    print(f"done. loaded games={total}")


if __name__ == "__main__":
    main()
