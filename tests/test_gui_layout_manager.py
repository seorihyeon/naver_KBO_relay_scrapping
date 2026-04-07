from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gui.layout_manager import compute_shell_layout


def test_compute_shell_layout_grows_alert_detail_when_error_debug_is_visible():
    without_error = compute_shell_layout(
        1440,
        940,
        bottom_panel_height=96,
        bottom_db_ratio=0.36,
        db_detail_window_width=980,
        db_detail_window_height=228,
        alert_detail_window_width=1040,
        alert_detail_window_height=336,
        error_detail_extra_height=104,
        show_error_detail=False,
    )
    with_error = compute_shell_layout(
        1440,
        940,
        bottom_panel_height=96,
        bottom_db_ratio=0.36,
        db_detail_window_width=980,
        db_detail_window_height=228,
        alert_detail_window_width=1040,
        alert_detail_window_height=336,
        error_detail_extra_height=104,
        show_error_detail=True,
    )

    assert with_error.alert_detail_window.height == without_error.alert_detail_window.height + 104
    assert with_error.main_window.width == without_error.main_window.width
    assert with_error.tab_content_width > 0
    assert with_error.tab_content_height > 0
