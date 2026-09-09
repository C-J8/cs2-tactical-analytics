from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.utils.text import clean_string


@dataclass(frozen=True)
class TeamRecord:
    team_id: str
    team_name: str
    aliases: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class PlayerMembership:
    player_id: str
    player_name: str
    aliases: tuple[str, ...]
    team_id: str
    valid_from: date | None
    valid_to: date | None
    source: str
    confidence: str


@dataclass(frozen=True)
class TeamRegistry:
    version: str
    teams: tuple[TeamRecord, ...]
    memberships: tuple[PlayerMembership, ...]
    source_path: Path

    def legacy_rosters(self) -> dict[str, set[str]]:
        """Expose the old team -> normalized player names contract during migration."""
        names_by_id = {team.team_id: team.team_name for team in self.teams}
        rosters: dict[str, set[str]] = {team.team_name: set() for team in self.teams}
        for membership in self.memberships:
            team_name = names_by_id[membership.team_id]
            values = {membership.player_name, *membership.aliases}
            rosters[team_name].update(normalize_name(value) for value in values if normalize_name(value))
        return rosters

    def team_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "team_registry_version": self.version,
                    "team_id": team.team_id,
                    "team_name": team.team_name,
                    "team_aliases": "|".join(team.aliases),
                    "source": team.source,
                }
                for team in self.teams
            ]
        )

    def membership_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "team_registry_version": self.version,
                    "player_id": row.player_id,
                    "player_name": row.player_name,
                    "player_aliases": "|".join(row.aliases),
                    "team_id": row.team_id,
                    "valid_from": row.valid_from,
                    "valid_to": row.valid_to,
                    "source": row.source,
                    "confidence": row.confidence,
                }
                for row in self.memberships
            ]
        )


def load_team_registry(path: Path) -> TeamRegistry:
    if not path.exists():
        raise FileNotFoundError(f"Team registry not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Team registry must be a YAML mapping: {path}")

    version = str(content.get("team_registry_version") or "legacy-v0")
    teams: list[TeamRecord] = []
    memberships: list[PlayerMembership] = []
    seen_team_ids: set[str] = set()
    for team_data in content.get("teams", []):
        team_name = clean_string(team_data.get("team_name"))
        if not team_name:
            continue
        team_id = normalize_id(team_data.get("team_id") or team_name)
        if team_id in seen_team_ids:
            raise ValueError(f"Duplicate team_id in registry: {team_id}")
        seen_team_ids.add(team_id)
        team_source = str(team_data.get("source") or content.get("default_source") or "manual_unverified")
        teams.append(
            TeamRecord(
                team_id=team_id,
                team_name=team_name,
                aliases=tuple(clean_string(value) for value in team_data.get("aliases", []) if clean_string(value)),
                source=team_source,
            )
        )
        for player_data in team_data.get("players", []):
            if isinstance(player_data, str):
                player_data = {"player_name": player_data}
            player_name = clean_string(player_data.get("player_name") or player_data.get("name"))
            if not player_name:
                continue
            memberships.append(
                PlayerMembership(
                    player_id=normalize_id(player_data.get("player_id") or player_name),
                    player_name=player_name,
                    aliases=tuple(
                        clean_string(value) for value in player_data.get("aliases", []) if clean_string(value)
                    ),
                    team_id=team_id,
                    valid_from=parse_date(player_data.get("valid_from")),
                    valid_to=parse_date(player_data.get("valid_to")),
                    source=str(player_data.get("source") or team_source),
                    confidence=str(player_data.get("confidence") or "manual_unverified"),
                )
            )
    validate_registry(teams, memberships)
    return TeamRegistry(version=version, teams=tuple(teams), memberships=tuple(memberships), source_path=path)


def validate_registry(teams: list[TeamRecord], memberships: list[PlayerMembership]) -> None:
    team_ids = {team.team_id for team in teams}
    for membership in memberships:
        if membership.team_id not in team_ids:
            raise ValueError(f"Membership references unknown team_id: {membership.team_id}")
        if membership.valid_from and membership.valid_to and membership.valid_from > membership.valid_to:
            raise ValueError(
                f"Invalid membership interval for {membership.player_name}/{membership.team_id}: "
                f"{membership.valid_from} > {membership.valid_to}"
            )


def registry_audit(registry: TeamRegistry) -> pd.DataFrame:
    memberships = registry.membership_frame()
    duplicate_player_ids = memberships.groupby("player_id")["team_id"].nunique() if not memberships.empty else pd.Series()
    boundary_rows = (
        memberships["valid_from"].notna() | memberships["valid_to"].notna() if not memberships.empty else pd.Series(dtype=bool)
    )
    return pd.DataFrame(
        [
            {
                "team_registry_version": registry.version,
                "team_count": len(registry.teams),
                "membership_count": len(registry.memberships),
                "player_count": int(memberships["player_id"].nunique()) if not memberships.empty else 0,
                "players_with_multiple_teams": int((duplicate_player_ids > 1).sum()),
                "date_bounded_memberships": int(boundary_rows.sum()),
                "unverified_memberships": int((memberships["confidence"] == "manual_unverified").sum())
                if not memberships.empty
                else 0,
            }
        ]
    )


def normalize_id(value: Any) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split())


def normalize_name(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value))
