"""Pure strike-zone rule resolution used by replay state builders."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_STRIKE_ZONE_RULES: dict[int, dict[str, float]] = {
    2024: {"top_pct": 0.5635, "bottom_pct": 0.2764, "width_cm": 47.18},
    2025: {"top_pct": 0.5575, "bottom_pct": 0.2704, "width_cm": 47.18},
}


@dataclass
class StrikeZoneRuleBook:
    """Resolves the effective strike-zone rule for a given season."""

    rules: dict[int, dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_STRIKE_ZONE_RULES))

    def get_rule(self, target_year: int | None) -> dict[str, float]:
        if not self.rules:
            self.rules = dict(DEFAULT_STRIKE_ZONE_RULES)
        rule_years = sorted(self.rules)
        if target_year is None:
            effective_year = rule_years[-1]
        else:
            past_years = [year for year in rule_years if year <= target_year]
            effective_year = past_years[-1] if past_years else rule_years[0]
        rule = dict(self.rules[effective_year])
        rule["effective_year"] = effective_year
        return rule

