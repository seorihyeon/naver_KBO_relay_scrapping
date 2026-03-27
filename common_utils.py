from __future__ import annotations

from typing import Any


EMPTY_VALUES = (None, "", "-", " ")


def first_non_empty(*values: Any) -> Any:
    """비어 있지 않은 첫 번째 값을 반환한다."""
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def to_int(value: Any, default: int | None = 0) -> int | None:
    """숫자/문자 섞인 값을 안전하게 int로 변환한다."""
    if value in EMPTY_VALUES:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return default
