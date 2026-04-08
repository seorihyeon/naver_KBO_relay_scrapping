import importlib.metadata as importlib_metadata
from functools import partial

import dearpygui.dearpygui as dpg

from dpg_utils import bind_korean_font
from gui.tags import GLOBAL_TAGS


def _show_window(shell, tag: str, sender=None, app_data=None, user_data=None) -> None:
    shell.show_window(tag)


def _hide_window(shell, tag: str, sender=None, app_data=None, user_data=None) -> None:
    shell.hide_window(tag)


def _show_recent_error(shell, sender=None, app_data=None, user_data=None) -> None:
    shell.state.show_recent_error()


def build_shell_ui(shell) -> None:
    shell._callbacks = {
        "connect_db": shell.ingestion_tab.connect_db,
        "show_db_detail": partial(_show_window, shell, GLOBAL_TAGS.db_detail_window),
        "show_alert_detail": partial(_show_window, shell, GLOBAL_TAGS.alert_detail_window),
        "close_db_detail": partial(_hide_window, shell, GLOBAL_TAGS.db_detail_window),
        "close_alert_detail": partial(_hide_window, shell, GLOBAL_TAGS.alert_detail_window),
        "show_recent_error": partial(_show_recent_error, shell),
        "toggle_error_detail": shell.state.toggle_error_detail,
        "tab_change": shell.on_tab_change,
        "viewport_resize": shell.layout_manager.on_viewport_resize,
        "recent_error_hotkey": partial(_show_recent_error, shell),
    }
    dpg.create_context()
    shell.status_window.build(
        on_connect_db=shell._callbacks["connect_db"],
        on_show_detail=shell._callbacks["show_db_detail"],
    )
    with dpg.window(
        tag=GLOBAL_TAGS.main_window,
        label=shell.viewport_title,
        width=shell.default_viewport_w - 20,
        height=shell.default_viewport_h - 420,
        pos=(10, 150),
        no_resize=True,
        no_move=True,
    ):
        with dpg.tab_bar(tag=GLOBAL_TAGS.main_tab_bar, callback=shell._callbacks["tab_change"]):
            for tab in shell.tabs:
                tab.build(parent=GLOBAL_TAGS.main_tab_bar)
    shell.alert_window.build(
        on_show_detail=shell._callbacks["show_alert_detail"],
        on_show_recent_error=shell._callbacks["show_recent_error"],
    )
    shell.db_detail_window.build(
        default_dsn=shell.state.default_dsn,
        on_connect_db=shell._callbacks["connect_db"],
        on_close=shell._callbacks["close_db_detail"],
    )
    shell.alert_detail_window.build(
        on_show_recent_error=shell._callbacks["show_recent_error"],
        on_toggle_error_detail=shell._callbacks["toggle_error_detail"],
        on_close=shell._callbacks["close_alert_detail"],
    )
    with dpg.handler_registry():
        dpg.add_key_press_handler(key=dpg.mvKey_F8, callback=shell._callbacks["recent_error_hotkey"])
    # DearPyGui 2.1.0 on Windows can crash on the first frame when the native
    # viewport title contains Korean text. Start with an ASCII-safe title and
    # promote it to the localized title after the first rendered frame.
    dpg.create_viewport(title=shell.safe_viewport_title, width=shell.default_viewport_w, height=shell.default_viewport_h)
    dpg.setup_dearpygui()
    bind_korean_font(size=16)
    try:
        dpg_version = importlib_metadata.version("dearpygui")
    except Exception:
        dpg_version = "unknown"
    if dpg_version != "unknown" and dpg_version <= "2.1.0":
        shell.state.set_status(
            "warn",
            "DearPyGui 한글 IME 경고",
            f"DearPyGui {dpg_version} 버전이 감지되었습니다. 이 버전에서는 Windows 한글 IME 입력이 불안정할 수 있습니다.",
            source="GUI",
        )
    shell.state.set_db_connection_indicator("연결 안 됨", "warn")
    shell.state.sync_presenter()
    dpg.set_viewport_resize_callback(shell._callbacks["viewport_resize"])
    dpg.show_viewport()
    shell.layout_manager.mark_dirty()
