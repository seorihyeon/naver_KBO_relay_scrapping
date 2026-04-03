from __future__ import annotations

import os
from pathlib import Path

import dearpygui.dearpygui as dpg
from PIL import Image

DPG_UTIL_TEXTURE_REGISTRY = "__dpg_utils_texture_registry"
TEXTURE_SHAPES = {}


def bind_korean_font(size=16, candidates=None):
    if candidates is None:
        candidates = [
            r"fonts/NanumGothic.otf",
            r"fonts/NanumGothic.ttf",
        ]

    font_path = next((p for p in candidates if os.path.exists(p)), None)
    if not font_path:
        print("[WARN] 한글 폰트를 찾지 못했습니다.")
        return None

    with dpg.font_registry():
        with dpg.font(font_path, size) as korean_font:
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Korean)

    dpg.bind_font(korean_font)
    return korean_font


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

        try:
            dpg.delete_item(tex_tag)
            TEXTURE_SHAPES.pop(tex_tag, None)
        except Exception:
            tex_tag = f"{tex_tag}_{width}x{height}"

    dpg.add_dynamic_texture(width, height, rgba_data, tag=tex_tag, parent=DPG_UTIL_TEXTURE_REGISTRY)
    TEXTURE_SHAPES[tex_tag] = (width, height)
    return tex_tag


def load_image_pixels(image_path, width, height, base_dir=None):
    p = Path(image_path)
    if not p.is_absolute():
        p = Path(base_dir) / p if base_dir else p
    p = p.resolve()
    if not p.exists():
        raise FileNotFoundError(f"이미지 파일 없음: {p}")

    img = Image.open(p).convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
    pixels = []
    for r, g, b, a in img.getdata():
        pixels.extend([r / 255.0, g / 255.0, b / 255.0, a / 255.0])

    return pixels, p
