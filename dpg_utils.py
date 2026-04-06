from __future__ import annotations

import os
from pathlib import Path

import dearpygui.dearpygui as dpg
from PIL import Image

DPG_UTIL_TEXTURE_REGISTRY = "__dpg_utils_texture_registry"
TEXTURE_SHAPES = {}


def bind_korean_font(size=16, candidates=None):
    base_dir = Path(__file__).resolve().parent
    if candidates is None:
        candidates = [
            base_dir / "fonts" / "NanumGothic.otf",
            base_dir / "fonts" / "NanumGothic.ttf",
            Path(r"C:\Windows\Fonts\malgun.ttf"),
            Path(r"C:\Windows\Fonts\malgunbd.ttf"),
            Path(r"C:\Windows\Fonts\gulim.ttc"),
        ]

    resolved_candidates: list[Path] = []
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute():
            resolved_candidates.append(path)
            continue
        resolved_candidates.append((base_dir / path).resolve())
        resolved_candidates.append(path.resolve())

    font_path = next((str(path) for path in resolved_candidates if os.path.exists(path)), None)
    if not font_path:
        print("[WARN] Korean font not found")
        return None

    with dpg.font_registry():
        with dpg.font(font_path, size) as korean_font:
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Korean)

    dpg.bind_font(korean_font)
    return korean_font


def prompt_native_text(*, title: str, initial_value: str = "", multiline: bool = False) -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog
        from tkinter.scrolledtext import ScrolledText
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result: dict[str, str | None] = {"value": None}

    try:
        if not multiline:
            value = simpledialog.askstring(title=title, prompt=title, initialvalue=initial_value, parent=root)
            return value

        dialog = tk.Toplevel(root)
        dialog.title(title)
        dialog.geometry("720x420")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        text = ScrolledText(dialog, wrap="word", font=("Malgun Gothic", 12))
        text.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        text.insert("1.0", initial_value or "")
        text.focus_set()

        button_row = tk.Frame(dialog)
        button_row.pack(fill="x", padx=12, pady=(0, 12))

        def on_ok(_event=None):
            result["value"] = text.get("1.0", "end-1c")
            dialog.destroy()

        def on_cancel(_event=None):
            dialog.destroy()

        ok_btn = tk.Button(button_row, text="OK", width=10, command=on_ok)
        ok_btn.pack(side="right")
        cancel_btn = tk.Button(button_row, text="Cancel", width=10, command=on_cancel)
        cancel_btn.pack(side="right", padx=(0, 8))

        dialog.bind("<Control-Return>", on_ok)
        dialog.bind("<Escape>", on_cancel)
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        root.wait_window(dialog)
        return result["value"]
    finally:
        root.destroy()


def create_or_replace_dynamic_texture(tex_tag, width, height, rgba_data):
    if not dpg.does_item_exist(DPG_UTIL_TEXTURE_REGISTRY):
        dpg.add_texture_registry(tag=DPG_UTIL_TEXTURE_REGISTRY, show=False)

    if dpg.does_item_exist(tex_tag):
        prev_shape = TEXTURE_SHAPES.get(tex_tag)
        try:
            if prev_shape == (width, height):
                dpg.set_value(tex_tag, rgba_data)
                return tex_tag
        except Exception:
            pass

    new_tag = dpg.generate_uuid()
    dpg.add_dynamic_texture(width, height, rgba_data, tag=new_tag, parent=DPG_UTIL_TEXTURE_REGISTRY)
    TEXTURE_SHAPES[new_tag] = (width, height)
    return new_tag


def load_image_pixels(image_path, width, height, base_dir=None):
    p = Path(image_path)
    if not p.is_absolute():
        p = Path(base_dir) / p if base_dir else p
    p = p.resolve()
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {p}")

    img = Image.open(p).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
    pixels = []
    for r, g, b, a in img.getdata():
        pixels.extend([r / 255.0, g / 255.0, b / 255.0, a / 255.0])

    return pixels, p
