from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
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
    notification_lines: list[str] = field(default_factory=list)
    active_tab: str = "데이터 수집"
    last_error_summary: str = ""
    last_error_debug: str = ""
    last_update_at: str = "-"

    default_dsn: str = ""
    default_image_path: str = "assets/stadium.png"
    default_data_dir: str = "example"
    default_schema_path: str = "sql/schema.sql"
    strike_zone_rules: dict[int, dict[str, float]] = field(default_factory=dict)

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
        raw_rules = config.get("strike_zone_rules", {})
        normalized_rules: dict[int, dict[str, float]] = {}
        for year, rule in raw_rules.items():
            try:
                normalized_rules[int(year)] = {
                    "top_pct": float(rule["top_pct"]),
                    "bottom_pct": float(rule["bottom_pct"]),
                    "width_cm": float(rule["width_cm"]),
                }
            except Exception:
                continue
        if not normalized_rules:
            normalized_rules = {
                2024: {"top_pct": 0.5635, "bottom_pct": 0.2764, "width_cm": 47.18},
                2025: {"top_pct": 0.5575, "bottom_pct": 0.2704, "width_cm": 47.18},
            }
        state.strike_zone_rules = normalized_rules
        return state

    def get_strike_zone_rule(self, target_year: int | None) -> dict[str, float]:
        if not self.strike_zone_rules:
            self.strike_zone_rules = {
                2024: {"top_pct": 0.5635, "bottom_pct": 0.2764, "width_cm": 47.18},
                2025: {"top_pct": 0.5575, "bottom_pct": 0.2704, "width_cm": 47.18},
            }

        rule_years = sorted(self.strike_zone_rules)
        if target_year is None:
            effective_year = rule_years[-1]
        else:
            past_years = [year for year in rule_years if year <= target_year]
            effective_year = past_years[-1] if past_years else rule_years[0]

        rule = dict(self.strike_zone_rules[effective_year])
        rule["effective_year"] = effective_year
        return rule

    def set_active_tab(self, tab_name: str) -> None:
        self.active_tab = tab_name
        if dpg.does_item_exist("global_status_current_tab"):
            dpg.set_value("global_status_current_tab", f"현재 탭: {tab_name}")

    def _status_color(self, channel: str) -> tuple[int, int, int]:
        if channel == "error":
            return (255, 110, 110)
        if channel == "warn":
            return (255, 195, 90)
        return (120, 220, 140)

    def _status_label(self, channel: str) -> str:
        return {"info": "성공/진행", "warn": "경고", "error": "실패"}.get(channel, channel)

    def _format_notification_line(self, channel: str, source: str, summary: str, user_detail: str | None) -> str:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        detail_part = f" | {user_detail}" if user_detail else ""
        return f"[{timestamp}] [{channel.upper()}] [{source}] {summary}{detail_part}"

    def _refresh_notification_panel(self) -> None:
        if dpg.does_item_exist("global_notification_text"):
            dpg.set_value("global_notification_text", "\n".join(self.notification_lines[-300:]))

    def _refresh_error_panel(self) -> None:
        if dpg.does_item_exist("recent_error_summary"):
            dpg.set_value("recent_error_summary", self.last_error_summary or "최근 오류 없음")
        if dpg.does_item_exist("recent_error_detail_summary"):
            dpg.set_value("recent_error_detail_summary", self.last_error_summary or "최근 오류 없음")
        if dpg.does_item_exist("global_error_debug_text"):
            dpg.set_value("global_error_debug_text", self.last_error_debug or "디버그 상세 없음")

    def set_db_connection_indicator(self, text: str, channel: str = "warn") -> None:
        if dpg.does_item_exist("db_connection_summary_text"):
            dpg.set_value("db_connection_summary_text", text)
            dpg.configure_item("db_connection_summary_text", color=self._status_color(channel))

    def toggle_error_detail(self) -> None:
        if dpg.does_item_exist("alert_detail_window"):
            dpg.configure_item("alert_detail_window", show=True)
        if not dpg.does_item_exist("error_detail_group"):
            return
        visible = dpg.is_item_shown("error_detail_group")
        dpg.configure_item("error_detail_group", show=not visible)

    def show_recent_error(self) -> None:
        self._refresh_error_panel()
        if dpg.does_item_exist("alert_detail_window"):
            dpg.configure_item("alert_detail_window", show=True)
        if dpg.does_item_exist("error_detail_group"):
            dpg.configure_item("error_detail_group", show=True)

    def set_status(
        self,
        channel: str,
        summary: str,
        user_detail: str | None = None,
        *,
        debug_detail: str | None = None,
        source: str = "공통",
        append: bool = True,
    ) -> None:
        self.last_update_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        merged_detail = user_detail
        if debug_detail:
            merged_detail = f"{user_detail}\n[debug] {debug_detail}" if user_detail else f"[debug] {debug_detail}"

        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", summary)
            dpg.configure_item("status_text", color=self._status_color(channel))

        if merged_detail is not None and dpg.does_item_exist("status_detail_text"):
            if append:
                self.status_logs.append(merged_detail)
            else:
                self.status_logs = [merged_detail]
            dpg.set_value("status_detail_text", "\n".join(self.status_logs[-200:]))

        notification = self._format_notification_line(channel, source, summary, user_detail)
        self.notification_lines.append(notification)
        self._refresh_notification_panel()

        if channel == "error":
            self.last_error_summary = user_detail or summary
            self.last_error_debug = debug_detail or user_detail or summary
            self._refresh_error_panel()

        if dpg.does_item_exist("global_status_recent_task"):
            dpg.set_value("global_status_recent_task", f"최근 작업: {source} | {summary}")
        if dpg.does_item_exist("global_status_result"):
            dpg.set_value("global_status_result", f"상태: {self._status_label(channel)}")
            dpg.configure_item("global_status_result", color=self._status_color(channel))
        if dpg.does_item_exist("global_status_updated_at"):
            dpg.set_value("global_status_updated_at", f"마지막 업데이트: {self.last_update_at}")
