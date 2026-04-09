"""Filesystem adapters for saved game JSON, anomaly outputs, and audit logs."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


Validator = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class CollectionRunPaths:
    save_dir: Path
    anomaly_dir: Path
    debug_log_path: Path
    anomaly_log_path: Path
    failure_log_path: Path


class JsonGameRepository:
    """Handles JSON persistence and collection-side log file management."""

    def prepare_collection_run(self, save_dir: Path) -> CollectionRunPaths:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = save_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return CollectionRunPaths(
            save_dir=save_dir,
            anomaly_dir=save_dir / "_anomalies",
            debug_log_path=save_dir / f"scrape_debug_{timestamp}.log",
            anomaly_log_path=logs_dir / f"collection_anomalies_{timestamp}.jsonl",
            failure_log_path=logs_dir / f"collection_failures_{timestamp}.jsonl",
        )

    def build_target_path(self, base_dir: Path, *, season_year: int, file_name: str) -> Path:
        path = base_dir / str(season_year) / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_pretty_json(self, path: Path, payload_text: str) -> None:
        path.write_text(payload_text, encoding="utf-8")

    def try_reuse_existing(self, path: Path, validator: Validator) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validation = validator(payload)
        except Exception:
            return None
        return validation if validation.get("ok") else None

    def append_debug_log(self, path: Path, message: str) -> None:
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
