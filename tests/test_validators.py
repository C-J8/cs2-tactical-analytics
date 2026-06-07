from datetime import date
from pathlib import Path

import pandas as pd

from src.config.schemas import load_maps_config, load_project_config, load_teams_config
from src.ingestion.validators import (
    canonicalize_map,
    canonicalize_team,
    find_duplicate_keys,
    identify_opponent,
    transform_match_catalog,
)
from src.utils.io import write_catalog


def _configs():
    return (
        load_project_config(Path("configs/project.yaml")),
        load_teams_config(Path("configs/teams.yaml")),
        load_maps_config(Path("configs/maps.yaml")),
    )


def test_standardize_team_alias() -> None:
    _, teams, _ = _configs()
    assert canonicalize_team("Team Vitality", teams) == "Vitality"


def test_standardize_map_alias() -> None:
    _, _, maps = _configs()
    assert canonicalize_map("de_mirage", maps) == "Mirage"


def test_detect_duplicate_keys() -> None:
    df = pd.DataFrame(
        {
            "hltv_match_id": ["1", "1", "2"],
            "map_name": ["Mirage", "Mirage", "Mirage"],
            "map_number": [1, 1, 1],
        }
    )
    assert find_duplicate_keys(df).tolist() == [True, True, False]


def test_generate_opponent_correctly() -> None:
    assert identify_opponent("Vitality", "NAVI", "Vitality") == "NAVI"
    assert identify_opponent("NAVI", "Vitality", "Vitality") == "NAVI"


def test_transform_and_save_csv_parquet(tmp_path: Path) -> None:
    project, teams, maps = _configs()
    df = pd.DataFrame(
        [
            {
                "hltv_match_id": "42",
                "match_url": "https://www.hltv.org/matches/42/example",
                "match_date": "2026-01-01",
                "event_name": "Example",
                "team_1": "Team Vitality",
                "team_2": "NAVI",
                "map_name": "de_mirage",
                "map_number": "1",
                "demo_link": "",
            }
        ]
    )

    catalog = transform_match_catalog(df, project, teams, maps)
    outputs = write_catalog(catalog, tmp_path, ["csv", "parquet"])

    assert catalog.loc[0, "series_id"] == "hltv_42"
    assert catalog.loc[0, "match_date"] == date(2026, 1, 1)
    assert catalog.loc[0, "opponent"] == "NAVI"
    assert catalog.loc[0, "validation_status"] == "ok"
    assert outputs["csv"].exists()
    assert outputs["parquet"].exists()


def test_transform_preserves_row_level_source_method() -> None:
    project, teams, maps = _configs()
    df = pd.DataFrame(
        [
            {
                "hltv_match_id": "43",
                "match_url": "https://www.hltv.org/matches/43/example",
                "match_date": "2026-01-02",
                "event_name": "Example",
                "team_1": "Vitality",
                "team_2": "NAVI",
                "map_name": "Mirage",
                "map_number": "1",
                "demo_link": "",
                "source_method": "manual+scrape",
            }
        ]
    )

    catalog = transform_match_catalog(df, project, teams, maps, source_method="manual")

    assert catalog.loc[0, "source_method"] == "manual+scrape"
