"""저장된 게임 JSON 검증용 CLI 엔트리포인트."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.kbo_ingest.game_validation import collect_json_files, validate_json_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="저장된 KBO 게임 JSON을 검증합니다.")
    parser.add_argument(
        "path",
        nargs="?",
        default="games",
        help="검사할 JSON 파일 또는 디렉터리입니다. 기본값은 games 입니다.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    target = Path(args.path)
    files = collect_json_files(target)
    if not files:
        print(f"검사할 JSON 파일이 없습니다: {target}")
        return 1

    total = len(files)
    ok_count = 0
    warning_count = 0
    fail_count = 0

    for json_file in files:
        result = validate_json_file(json_file)
        if result["ok"]:
            ok_count += 1
            if result["warnings"]:
                warning_count += 1
                print(f"[WARN] {result['file']}")
                for message in result["warnings"]:
                    print(f"   - {message}")
            else:
                print(f"[OK] {result['file']}")
            continue

        fail_count += 1
        print(f"[FAIL] {result['file']}")
        for message in result["issues"]:
            print(f"   - {message}")
        if result["warnings"]:
            print("   [warnings]")
            for message in result["warnings"]:
                print(f"   - {message}")

    print()
    print(f"총 {total}개 파일 검사를 마쳤습니다.")
    print(f"  - 정상: {ok_count}")
    print(f"  - 경고만 있음: {warning_count}")
    print(f"  - 실패: {fail_count}")
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
