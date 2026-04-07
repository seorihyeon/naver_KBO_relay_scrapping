from __future__ import annotations

import re

from .models import EventRow, GameContext, PlayerInfo, ReplayDataset, RosterContext, SubstitutionRow


POSITION_ALIASES = {
    "1": "P",
    "투수": "P",
    "2": "C",
    "포수": "C",
    "3": "1B",
    "1루수": "1B",
    "4": "2B",
    "2루수": "2B",
    "5": "3B",
    "3루수": "3B",
    "6": "SS",
    "유격수": "SS",
    "7": "LF",
    "좌익수": "LF",
    "8": "CF",
    "중견수": "CF",
    "9": "RF",
    "우익수": "RF",
    "0": "DH",
    "지명타자": "DH",
}
POSITION_PATTERN = r"(투수|포수|1루수|2루수|3루수|유격수|좌익수|중견수|우익수)"


def canonical_position(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return POSITION_ALIASES.get(raw)


def build_roster_context(dataset: ReplayDataset) -> RosterContext:
    context = RosterContext()
    context.team_name_by_id = {
        dataset.context.home_team_id: dataset.context.home_team_name,
        dataset.context.away_team_id: dataset.context.away_team_name,
    }
    for player in dataset.players:
        context.player_name_by_id[player.player_id] = player.player_name
        if player.height_cm is not None:
            context.player_height_by_id[player.player_id] = player.height_cm
        if player.batting_side:
            context.player_batting_side_by_id[player.player_id] = player.batting_side

    for row in dataset.roster_entries:
        if row.team_id is None or not row.player_name:
            continue
        context.player_team_by_name[row.player_name] = row.team_id
        lineup = context.starting_defense_by_team.setdefault(row.team_id, {})
        position = canonical_position(row.field_position_code) or canonical_position(row.field_position_name)
        if row.is_starting_pitcher:
            lineup["P"] = row.player_name
        elif row.roster_group == "starter" and position and position != "DH":
            lineup[position] = row.player_name

    current_lineups = {team_id: lineup.copy() for team_id, lineup in context.starting_defense_by_team.items()}
    substitutions_by_event: dict[int, list[SubstitutionRow]] = {}
    for substitution in dataset.substitutions:
        if substitution.event_id is not None:
            substitutions_by_event.setdefault(substitution.event_id, []).append(substitution)

    for event in dataset.events:
        for substitution in substitutions_by_event.get(event.event_id, []):
            team_id = infer_substitution_target(substitution, context.player_team_by_name)
            if team_id is None:
                continue
            lineup = current_lineups.setdefault(team_id, {})
            parsed = parse_substitution_update(
                substitution.description,
                substitution.in_player_name,
                substitution.out_player_name,
                substitution.in_position,
                substitution.out_position,
            )
            if not parsed:
                continue
            position, player_name = parsed
            if not position or position == "DH" or not player_name:
                continue
            clear_player_from_lineup(lineup, player_name)
            lineup[position] = player_name
        context.defense_snapshots_by_event[event.event_id] = {
            team_id: lineup.copy() for team_id, lineup in current_lineups.items()
        }
    return context


def clear_player_from_lineup(lineup: dict[str, str], player_name: str) -> None:
    for position, name in list(lineup.items()):
        if name == player_name:
            del lineup[position]


def infer_substitution_target(substitution: SubstitutionRow, player_team_by_name: dict[str, int]) -> int | None:
    if substitution.team_id is not None:
        return substitution.team_id
    for name in (substitution.in_player_name, substitution.out_player_name):
        if name and name in player_team_by_name:
            return player_team_by_name[name]
    replacement = parse_substitution_update(
        substitution.description,
        substitution.in_player_name,
        substitution.out_player_name,
        substitution.in_position,
        substitution.out_position,
    )
    if replacement and replacement[1] in player_team_by_name:
        return player_team_by_name[replacement[1]]
    return None


def parse_substitution_update(
    description: str | None,
    in_name: str | None = None,
    out_name: str | None = None,
    in_position: str | None = None,
    out_position: str | None = None,
) -> tuple[str | None, str | None] | None:
    position = canonical_position(in_position) or canonical_position(out_position)
    if position and in_name and position != "DH":
        return position, in_name
    if not description:
        return None

    change_match = re.search(
        rf"^(?:.+?)\s(?P<name>[^ :]+)\s*:\s*(?P<position>{POSITION_PATTERN}).*수비위치 변경",
        description,
    )
    if change_match:
        return canonical_position(change_match.group("position")), change_match.group("name")

    replace_match = re.search(
        rf"^(?P<old_position>{POSITION_PATTERN})\s(?P<old_name>[^ :]+)\s*:\s*(?P<new_position>{POSITION_PATTERN})\s(?P<new_name>[^ ]+)\s+\(.+\)로 교체",
        description,
    )
    if replace_match:
        return canonical_position(replace_match.group("new_position")), replace_match.group("new_name")

    pitcher_match = re.search(r"^투수\s(?P<old_name>[^ :]+)\s*:\s*투수\s(?P<new_name>[^ ]+)\s+\(.+\)로 교체", description)
    if pitcher_match:
        return "P", pitcher_match.group("new_name")
    return None


def get_lineup_snapshot(event_id: int, team_id: int | None, roster_context: RosterContext) -> dict[str, str]:
    snapshot = roster_context.defense_snapshots_by_event.get(event_id, {})
    lineup = snapshot.get(team_id)
    if lineup is not None:
        return lineup
    return roster_context.starting_defense_by_team.get(team_id or -1, {})
