from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TagNamespace:
    prefix: str
    separator: str = "::"

    def tag(self, name: str) -> str:
        return f"{self.prefix}{self.separator}{name}"

    __call__ = tag

    def child(self, suffix: str) -> "TagNamespace":
        return TagNamespace(f"{self.prefix}{self.separator}{suffix}", self.separator)


@dataclass(frozen=True)
class GlobalTagSet:
    main_window: str = "shell::main_window"
    main_tab_bar: str = "shell::main_tab_bar"
    db_window: str = "shell::db_window"
    alert_window: str = "shell::alert_window"
    db_detail_window: str = "shell::db_detail_window"
    alert_detail_window: str = "shell::alert_detail_window"
    db_summary_info_panel: str = "status::db_summary_info_panel"
    db_connection_summary_text: str = "status::db_connection_summary_text"
    status_text: str = "status::summary_text"
    status_detail_text: str = "status::detail_text"
    db_summary_hint_text: str = "status::hint_text"
    dsn_input: str = "status::dsn_input"
    global_status_current_tab: str = "alerts::current_tab"
    global_status_recent_task: str = "alerts::recent_task"
    global_status_result: str = "alerts::recent_result"
    global_status_updated_at: str = "alerts::updated_at"
    global_notification_text: str = "alerts::notification_text"
    recent_error_summary: str = "alerts::recent_error_summary"
    recent_error_detail_summary: str = "alerts::recent_error_detail_summary"
    global_error_debug_text: str = "alerts::error_debug_text"
    error_detail_group: str = "alerts::error_detail_group"


GLOBAL_TAGS = GlobalTagSet()
