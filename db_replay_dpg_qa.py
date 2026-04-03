"""Backward-compatible entrypoint for the integrated DPG app.

The tabbed implementation now lives in `kbo_integrated_gui.py` + `tabs/` modules.
"""

from kbo_integrated_gui import KBOIntegratedDPGApp


ReplayDPGQA = KBOIntegratedDPGApp


if __name__ == "__main__":
    app = KBOIntegratedDPGApp()
    app.build()
