"""Service adapters around product validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.kbo_ingest.game_validation import validate_game


@dataclass(frozen=True)
class GameValidationResult:
    ok: bool
    issues: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": list(self.issues),
            "warnings": list(self.warnings),
        }


class ValidationService:
    """Wraps the repository's canonical game validation entry point."""

    def validate_payload(self, payload: dict[str, Any]) -> GameValidationResult:
        result = validate_game(payload)
        return GameValidationResult(
            ok=bool(result.get("ok")),
            issues=list(result.get("issues") or []),
            warnings=list(result.get("warnings") or []),
        )

    def validate_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.validate_payload(payload).as_dict()
