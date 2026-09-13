from pathlib import Path

from src.teams.registry import load_team_registry, registry_audit


def test_team_registry_builds_canonical_and_legacy_views(tmp_path: Path) -> None:
    path = tmp_path / "teams.yaml"
    path.write_text(
        """
team_registry_version: v1
teams:
  - team_id: vitality
    team_name: Vitality
    aliases: [Team Vitality]
    players:
      - player_name: ZywOo
        aliases: [zywoo]
  - team_id: falcons
    team_name: Falcons
    players:
      - player_name: ZywOo
""",
        encoding="utf-8",
    )

    registry = load_team_registry(path)

    assert registry.version == "v1"
    assert registry.legacy_rosters()["Vitality"] == {"zywoo"}
    assert registry.team_frame()["team_id"].tolist() == ["vitality", "falcons"]
    assert registry_audit(registry).iloc[0]["players_with_multiple_teams"] == 1
