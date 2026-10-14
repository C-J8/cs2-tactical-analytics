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


def test_team_scoped_audit_requires_source_date_and_verified_confidence(tmp_path: Path) -> None:
    path = tmp_path / "teams.yaml"
    path.write_text(
        """
team_registry_version: v1
teams:
  - team_id: vitality
    team_name: Vitality
    players:
      - player_name: ZywOo
        valid_from: 2025-01-10
        source: https://example.test/official-roster
        confidence: verified_primary
      - player_name: apEX
""",
        encoding="utf-8",
    )

    audit = registry_audit(load_team_registry(path), team_id="vitality").iloc[0]

    assert audit["scoped_membership_count"] == 2
    assert audit["verified_memberships"] == 1
    assert audit["unverified_memberships"] == 1
