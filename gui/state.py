from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Callable

import dearpygui.dearpygui as dpg

from .tags import GLOBAL_TAGS


@dataclass(frozen=True)
class GameOption:
    game_id: int
    label: str


@dataclass
class NotificationEntry:
    channel: str
    source: str
    summary: str
    detail: str | None = None
    created_at: dt.datetime = field(default_factory=dt.datetime.now)

    def format_line(self) -> str:
        detail_part = f" | {self.detail}" if self.detail else ""
        timestamp = self.created_at.strftime("%H:%M:%S")
        return f"[{timestamp}] [{self.channel.upper()}] [{self.source}] {self.summary}{detail_part}"


@dataclass
class AppStateModel:
    config: dict[str, Any]
    conn: Any = None
    games: list[GameOption] = field(default_factory=list)
    game_id: int | None = None
    status_logs: list[str] = field(default_factory=list)
    notifications: list[NotificationEntry] = field(default_factory=list)
    active_tab: str = "수집"
    last_error_summary: str = ""
    last_error_debug: str = ""
    last_update_at: str = "-"
    default_dsn: str = ""
    default_image_path: str = "assets/stadium.png"
    default_data_dir: str = "example"
    default_schema_path: str = "sql/schema.sql"
    strike_zone_rules: dict[int, dict[str, float]] = field(default_factory=dict)
    db_indicator_text: str = "연결 안 됨"
    db_indicator_channel: str = "warn"
    last_status_channel: str = "info"
    last_status_summary: str = "대기 중"
    last_status_detail: str | None = None
    recent_task_text: str = "최근 작업: 없음"
    recent_result_text: str = "대기 중"


def _default_strike_zone_rules() -> dict[int, dict[str, float]]:
    return {
        2024: {"top_pct": 0.5635, "bottom_pct": 0.2764, "width_cm": 47.18},
        2025: {"top_pct": 0.5575, "bottom_pct": 0.2704, "width_cm": 47.18},
    }


def _load_config(root_dir: Path) -> dict[str, Any]:
    cfg_env = os.environ.get("KBO_APP_CONFIG")
    candidates: list[Path] = []
    if cfg_env:
        candidates.append(Path(cfg_env))
    candidates.append(root_dir / "config" / "app_config.json")

    for cfg_path in candidates:
        if not cfg_path.exists():
            continue
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _build_model(config: dict[str, Any]) -> AppStateModel:
    model = AppStateModel(config=config)
    model.default_dsn = config.get("db", {}).get("dsn", "postgresql://HOST:PASSWORD@HOST:5432/DBNAME")
    model.default_image_path = config.get("paths", {}).get("image_path", "assets/stadium.png")
    model.default_data_dir = config.get("paths", {}).get("json_data_dir", "example")
    model.default_schema_path = config.get("paths", {}).get("schema_path", "sql/schema.sql")
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
    model.strike_zone_rules = normalized_rules or _default_strike_zone_rules()
    model.recent_result_text = "대기 중"
    model.db_indicator_text = "연결 안 됨"
    return model


class AppStatePresenter:
    def _status_color(self, channel: str) -> tuple[int, int, int]:
        if channel == "error":
            return (255, 110, 110)
        if channel == "warn":
            return (255, 195, 90)
        return (120, 220, 140)

    def _status_label(self, channel: str) -> str:
        return {"info": "정상 / 진행 중", "warn": "경고", "error": "실패"}.get(channel, channel)

    def render(self, model: AppStateModel) -> None:
        self.render_active_tab(model)
        self.render_status(model)
        self.render_notifications(model)
        self.render_errors(model)
        self.render_db_indicator(model)

    def render_active_tab(self, model: AppStateModel) -> None:
        if dpg.does_item_exist(GLOBAL_TAGS.global_status_current_tab):
            dpg.set_value(GLOBAL_TAGS.global_status_current_tab, f"현재 탭: {model.active_tab}")

    def render_notifications(self, model: AppStateModel) -> None:
        if dpg.does_item_exist(GLOBAL_TAGS.global_notification_text):
            lines = [entry.format_line() for entry in model.notifications[-300:]]
            dpg.set_value(GLOBAL_TAGS.global_notification_text, "\n".join(lines))

    def render_errors(self, model: AppStateModel) -> None:
        summary = model.last_error_summary or "최근 오류 없음"
        detail = model.last_error_debug or "디버그 상세 없음"
        if dpg.does_item_exist(GLOBAL_TAGS.recent_error_summary):
            dpg.set_value(GLOBAL_TAGS.recent_error_summary, summary)
        if dpg.does_item_exist(GLOBAL_TAGS.recent_error_detail_summary):
            dpg.set_value(GLOBAL_TAGS.recent_error_detail_summary, summary)
        if dpg.does_item_exist(GLOBAL_TAGS.global_error_debug_text):
            dpg.set_value(GLOBAL_TAGS.global_error_debug_text, detail)

    def render_db_indicator(self, model: AppStateModel) -> None:
        if dpg.does_item_exist(GLOBAL_TAGS.db_connection_summary_text):
            dpg.set_value(GLOBAL_TAGS.db_connection_summary_text, model.db_indicator_text)
            dpg.configure_item(
                GLOBAL_TAGS.db_connection_summary_text,
                color=self._status_color(model.db_indicator_channel),
            )

    def render_status(self, model: AppStateModel) -> None:
        if dpg.does_item_exist(GLOBAL_TAGS.status_text):
            dpg.set_value(GLOBAL_TAGS.status_text, model.last_status_summary)
            dpg.configure_item(GLOBAL_TAGS.status_text, color=self._status_color(model.last_status_channel))
        if dpg.does_item_exist(GLOBAL_TAGS.status_detail_text):
            dpg.set_value(GLOBAL_TAGS.status_detail_text, "\n".join(model.status_logs[-200:]))
        if dpg.does_item_exist(GLOBAL_TAGS.global_status_recent_task):
            dpg.set_value(GLOBAL_TAGS.global_status_recent_task, model.recent_task_text)
        if dpg.does_item_exist(GLOBAL_TAGS.global_status_result):
            dpg.set_value(
                GLOBAL_TAGS.global_status_result,
                f"상태: {self._status_label(model.last_status_channel)}",
            )
            dpg.configure_item(GLOBAL_TAGS.global_status_result, color=self._status_color(model.last_status_channel))
        if dpg.does_item_exist(GLOBAL_TAGS.global_status_updated_at):
            dpg.set_value(GLOBAL_TAGS.global_status_updated_at, f"마지막 업데이트: {model.last_update_at}")

    def show_recent_error(self, model: AppStateModel) -> None:
        self.render_errors(model)
        if dpg.does_item_exist(GLOBAL_TAGS.alert_detail_window):
            dpg.configure_item(GLOBAL_TAGS.alert_detail_window, show=True)
        if dpg.does_item_exist(GLOBAL_TAGS.error_detail_group):
            dpg.configure_item(GLOBAL_TAGS.error_detail_group, show=True)

    def toggle_error_detail(self) -> None:
        if dpg.does_item_exist(GLOBAL_TAGS.alert_detail_window):
            dpg.configure_item(GLOBAL_TAGS.alert_detail_window, show=True)
        if not dpg.does_item_exist(GLOBAL_TAGS.error_detail_group):
            return
        visible = dpg.is_item_shown(GLOBAL_TAGS.error_detail_group)
        dpg.configure_item(GLOBAL_TAGS.error_detail_group, show=not visible)


class AppState:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        presenter: AppStatePresenter | None = None,
        model: AppStateModel | None = None,
    ) -> None:
        object.__setattr__(self, "model", model or _build_model(config))
        object.__setattr__(self, "presenter", presenter or AppStatePresenter())
        object.__setattr__(self, "_listeners", defaultdict(list))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.model, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"model", "presenter", "_listeners"}:
            object.__setattr__(self, name, value)
            return
        setattr(self.model, name, value)

    @classmethod
    def from_environment(cls, root_dir: Path) -> "AppState":
        config = _load_config(root_dir)
        return cls(config=config)

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        self._listeners[event_name].append(callback)

    def _emit(self, event_name: str, payload: Any) -> None:
        for callback in list(self._listeners.get(event_name, [])):
            callback(payload)

    def sync_presenter(self) -> None:
        self.presenter.render(self.model)

    def get_strike_zone_rule(self, target_year: int | None) -> dict[str, float]:
        if not self.model.strike_zone_rules:
            self.model.strike_zone_rules = _default_strike_zone_rules()
        rule_years = sorted(self.model.strike_zone_rules)
        if target_year is None:
            effective_year = rule_years[-1]
        else:
            past_years = [year for year in rule_years if year <= target_year]
            effective_year = past_years[-1] if past_years else rule_years[0]
        rule = dict(self.model.strike_zone_rules[effective_year])
        rule["effective_year"] = effective_year
        return rule

    def set_active_tab(self, tab_name: str) -> None:
        self.model.active_tab = tab_name
        self.presenter.render_active_tab(self.model)
        self._emit("active_tab_changed", tab_name)

    def set_games(self, games: list[GameOption]) -> None:
        self.model.games = games
        self._emit("games_changed", games)

    def set_game_selection(self, game_id: int | None) -> None:
        self.model.game_id = game_id
        self._emit("game_selected", game_id)

    def set_db_connection_indicator(self, text: str, channel: str = "warn") -> None:
        self.model.db_indicator_text = text
        self.model.db_indicator_channel = channel
        self.presenter.render_db_indicator(self.model)

    def toggle_error_detail(self) -> None:
        self.presenter.toggle_error_detail()

    def show_recent_error(self) -> None:
        self.presenter.show_recent_error(self.model)

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
        self.model.last_update_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.model.last_status_channel = channel
        self.model.last_status_summary = summary
        self.model.last_status_detail = user_detail
        self.model.recent_task_text = f"최근 작업: {source} | {summary}"
        self.model.recent_result_text = channel

        merged_detail = user_detail
        if debug_detail:
            merged_detail = f"{user_detail}\n[debug] {debug_detail}" if user_detail else f"[debug] {debug_detail}"
        if merged_detail:
            if append:
                self.model.status_logs.append(merged_detail)
            else:
                self.model.status_logs = [merged_detail]

        notification = NotificationEntry(channel=channel, source=source, summary=summary, detail=user_detail)
        self.model.notifications.append(notification)

        if channel == "error":
            self.model.last_error_summary = user_detail or summary
            self.model.last_error_debug = debug_detail or user_detail or summary

        self.presenter.render_status(self.model)
        self.presenter.render_notifications(self.model)
        if channel == "error":
            self.presenter.render_errors(self.model)

        self._emit(
            "status_changed",
            {
                "channel": channel,
                "summary": summary,
                "detail": user_detail,
                "debug_detail": debug_detail,
                "source": source,
            },
        )
