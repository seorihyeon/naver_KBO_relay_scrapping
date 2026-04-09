"""최소 스키마 JSON 마이그레이션용 CLI 엔트리포인트."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from services.json_migration_service import iter_json_files, migrate_one_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="게임 JSON을 최소 스키마로 마이그레이션합니다.")
    parser.add_argument("path", nargs="?", default="games", help="대상 JSON 파일 또는 디렉터리입니다.")
    parser.add_argument("--in-place", action="store_true", help="백업과 패치를 남긴 뒤 원본 파일을 직접 갱신합니다.")
    parser.add_argument("--output-dir", type=Path, help="별도 출력 디렉터리에 변환 결과를 저장합니다.")
    parser.add_argument("--no-validate", action="store_true", help="변환 전후 검증을 생략합니다.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    target = Path(args.path)
    files = iter_json_files(target)
    if not files:
        print(f"대상 JSON 파일이 없습니다: {target}")
        return 1

    results = [
        migrate_one_file(
            path,
            write_in_place=bool(args.in_place),
            output_root=args.output_dir,
            relative_root=target if target.is_dir() else target.parent,
            validate=not args.no_validate,
        )
        for path in files
    ]

    changed_count = sum(1 for item in results if item["changed"])
    failed_after = [item for item in results if item["after_ok"] is False]

    print(f"files={len(results)} changed={changed_count} after_failures={len(failed_after)}")
    for item in results[:20]:
        print(
            f"- {item['path']} | changed={item['changed']} | "
            f"written={item['written_path'] or '-'} | after_ok={item['after_ok']}"
        )

    return 0 if not failed_after else 2


if __name__ == "__main__":
    raise SystemExit(main())
