from pathlib import Path

from src.config.schemas import load_maps_config, load_project_config, load_teams_config


def test_load_configs() -> None:
    project = load_project_config(Path("configs/project.yaml"))
    teams = load_teams_config(Path("configs/teams.yaml"))
    maps = load_maps_config(Path("configs/maps.yaml"))

    assert project.project_name == "cs2-tactical-analytics"
    assert project.mode == "manual"
    assert teams.teams[0].team_name == "Vitality"
    assert maps.maps[0].map_name == "Mirage"
