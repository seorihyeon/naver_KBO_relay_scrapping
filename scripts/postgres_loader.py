"""PostgreSQL 적재/검증용 CLI 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from services.postgres_loader_service import main


if __name__ == "__main__":
    raise SystemExit(main())
