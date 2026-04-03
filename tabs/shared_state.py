from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg


@dataclass
class AppState:
    config: dict[str, Any]
    conn: Any = None
    games: list[tuple[Any, str]] = field(default_factory=list)
    game_id: Any = None
    status_logs: list[str] = field(default_factory=list)

    default_dsn: str = ""
    default_image_path: str = "assets/stadium.png"
    default_data_dir: str = "example"
    default_schema_path: str = "sql/schema.sql"

    @classmethod
    def from_environment(cls, root_dir: Path) -> "AppState":
        cfg_env = os.environ.get("KBO_APP_CONFIG")
        candidates: list[Path] = []
        if cfg_env:
            candidates.append(Path(cfg_env))
        candidates.append(root_dir / "config" / "app_config.json")

        config: dict[str, Any] = {}
        for cfg_path in candidates:
            if not cfg_path.exists():
                continue
            try:
                config = json.loads(cfg_path.read_text(encoding="utf-8"))
                break
            except Exception:
                continue

        state = cls(config=config)
        state.default_dsn = config.get("db", {}).get("dsn", "postgresql://HOST:PASSWORD@HOST:5432/DBNAME")
        state.default_image_path = config.get("paths", {}).get("image_path", "assets/stadium.png")
        state.default_data_dir = config.get("paths", {}).get("json_data_dir", "example")
        state.default_schema_path = config.get("paths", {}).get("schema_path", "sql/schema.sql")
        return state

    def set_status(self, summary: str, detail: str | None = None, append: bool = False) -> None:
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", summary)

        if detail is None or not dpg.does_item_exist("status_detail_text"):
            return

        if append:
            self.status_logs.append(detail)
        else:
            self.status_logs = [detail]

        dpg.set_value("status_detail_text", "\n".join(self.status_logs))
