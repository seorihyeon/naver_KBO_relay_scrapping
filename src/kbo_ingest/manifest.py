from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .source_profile import build_source_profile


DEFAULT_SEASONS = ("2024", "2025")
DEFAULT_BATCH_SIZES = (10, 25, 50, 100, 250, 500)


def collect_season_files(data_dir: Path, seasons: tuple[str, ...] = DEFAULT_SEASONS) -> list[Path]:
    files: list[Path] = []
    for season in seasons:
        files.extend(sorted((data_dir / season).glob("*.json")))
    return files


def resolve_stage_sizes(total_count: int, requested_sizes: list[int] | None = None) -> list[int]:
    stage_sizes = list(requested_sizes or DEFAULT_BATCH_SIZES)
    normalized = sorted({size for size in stage_sizes if 0 < size < total_count})
    if total_count not in normalized:
        normalized.append(total_count)
    return normalized


def build_manifest(data_dir: Path, *, seasons: tuple[str, ...] = DEFAULT_SEASONS, seed: int = 20260404, project_root: Path | None = None) -> dict[str, Any]:
    project_root = project_root or Path.cwd()
    files = collect_season_files(data_dir, seasons)
    profiles = [build_source_profile(path, project_root=project_root) for path in files]
    rng = random.Random(seed)
    rng.shuffle(profiles)
    for index, profile in enumerate(profiles, start=1):
        profile["shuffle_index"] = index

    return {
        "seed": seed,
        "data_dir": data_dir.as_posix(),
        "seasons": list(seasons),
        "total_games": len(profiles),
        "entries": profiles,
    }


def write_manifest(manifest: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))
