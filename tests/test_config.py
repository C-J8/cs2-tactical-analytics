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


def test_feature_windows_config_reaches_115_and_keeps_0_15() -> None:
    project = load_project_config(Path("configs/project.yaml"))

    assert project.feature_windows.round_duration_seconds == 115
    assert (0, 15) in project.feature_windows.interval_windows
    assert (0, 15) in project.feature_windows.cumulative_windows
    assert max(end for _, end in project.feature_windows.interval_windows) == 115
    assert max(end for _, end in project.feature_windows.cumulative_windows) == 115
    assert project.feature_windows.interval_windows != project.feature_windows.cumulative_windows
