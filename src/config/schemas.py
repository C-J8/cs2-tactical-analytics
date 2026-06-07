from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class FeatureWindowsConfig(BaseModel):
    round_duration_seconds: int = Field(default=115, ge=1)
    interval_windows: list[tuple[int, int]] = Field(
        default_factory=lambda: [
            (0, 15),
            (15, 25),
            (25, 35),
            (35, 45),
            (45, 55),
            (55, 65),
            (65, 75),
            (75, 85),
            (85, 95),
            (95, 105),
            (105, 115),
        ]
    )
    cumulative_windows: list[tuple[int, int]] = Field(
        default_factory=lambda: [
            (0, 15),
            (0, 25),
            (0, 35),
            (0, 45),
            (0, 55),
            (0, 65),
            (0, 75),
            (0, 85),
            (0, 95),
            (0, 105),
            (0, 115),
        ]
    )

    @field_validator("interval_windows", "cumulative_windows", mode="before")
    @classmethod
    def coerce_windows(cls, values: list[list[int]] | list[tuple[int, int]]) -> list[tuple[int, int]]:
        return [tuple(value) for value in values]

    @model_validator(mode="after")
    def windows_are_valid(self) -> "FeatureWindowsConfig":
        for window_group in [self.interval_windows, self.cumulative_windows]:
            for start, end in window_group:
                if start < 0 or end <= start:
                    raise ValueError("feature windows must have non-negative start and end greater than start")
                if end > self.round_duration_seconds:
                    raise ValueError("feature windows cannot exceed round_duration_seconds")
        if (0, 15) not in self.interval_windows or (0, 15) not in self.cumulative_windows:
            raise ValueError("feature windows must include 0-15s in both interval and cumulative windows")
        if max(end for _, end in self.interval_windows) != self.round_duration_seconds:
            raise ValueError("interval windows must reach round_duration_seconds")
        if max(end for _, end in self.cumulative_windows) != self.round_duration_seconds:
            raise ValueError("cumulative windows must reach round_duration_seconds")
        return self


class ProjectConfig(BaseModel):
    project_name: str
    mode: Literal["manual", "scrape"] = "manual"
    date_start: date
    date_end: date
    target_maps: list[str] = Field(min_length=1)
    target_teams: list[str] = Field(min_length=1)
    output_formats: list[Literal["csv", "parquet"]] = Field(default_factory=lambda: ["csv", "parquet"])
    rate_limit_seconds: int = Field(default=5, ge=0)
    cache_enabled: bool = True
    manual_seed_path: Path = Path("data/raw/manual/matches_seed.csv")
    hltv_cache_dir: Path = Path("data/raw/hltv_pages")
    bronze_output_dir: Path = Path("data/bronze/match_catalog_raw")
    silver_output_dir: Path = Path("data/silver/matches_catalog")
    demo_archive_dir: Path = Path("data/raw/demo_archives")
    demo_output_dir: Path = Path("data/raw/demos")
    demo_manifest_dir: Path = Path("data/bronze/demo_manifest")
    download_timeout_seconds: int = Field(default=60, ge=1)
    download_rate_limit_seconds: int = Field(default=5, ge=0)
    max_downloads_per_run: int | None = Field(default=None, ge=1)
    extract_archives: bool = True
    force_download: bool = False
    demo_manifest_path: Path = Path("data/bronze/demo_manifest/demo_manifest.parquet")
    local_archive_manifest_dir: Path = Path("data/bronze/local_archive_manifest")
    dem_files_manifest_dir: Path = Path("data/bronze/dem_files_manifest")
    dem_files_manifest_path: Path = Path("data/bronze/dem_files_manifest/dem_files_manifest.parquet")
    parsed_bronze_dir: Path = Path("data/bronze/parsed_demos")
    parsed_silver_dir: Path = Path("data/silver/parsed_demos")
    parse_manifest_dir: Path = Path("data/bronze/parse_manifest")
    parser_backend: Literal["awpy"] = "awpy"
    player_rosters_path: Path = Path("configs/player_rosters.yaml")
    feature_windows: FeatureWindowsConfig = Field(default_factory=FeatureWindowsConfig)
    parse_player_props: list[str] = Field(
        default_factory=lambda: [
            "X",
            "Y",
            "Z",
            "health",
            "armor_value",
            "has_helmet",
            "has_defuser",
            "inventory",
        ]
    )
    parse_tables: list[str] = Field(
        default_factory=lambda: [
            "rounds",
            "kills",
            "damages",
            "shots",
            "bomb",
            "smokes",
            "infernos",
            "grenades",
            "footsteps",
            "ticks",
        ]
    )
    parse_events: bool = True
    max_demos_per_run: int | None = Field(default=None, ge=1)
    force_parse: bool = False

    @field_validator("target_maps", "target_teams", "output_formats")
    @classmethod
    def non_empty_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if str(value).strip()]
        if not cleaned:
            raise ValueError("must contain at least one non-empty value")
        return cleaned

    @model_validator(mode="after")
    def date_range_is_valid(self) -> "ProjectConfig":
        if self.date_start > self.date_end:
            raise ValueError("date_start must be before or equal to date_end")
        return self


class TeamConfig(BaseModel):
    team_name: str
    hltv_team_id: int | None = None
    aliases: list[str] = Field(default_factory=list)


class TeamsConfig(BaseModel):
    teams: list[TeamConfig] = Field(default_factory=list)


class MapConfig(BaseModel):
    map_name: str
    aliases: list[str] = Field(default_factory=list)


class MapsConfig(BaseModel):
    maps: list[MapConfig] = Field(default_factory=list)


class CatalogRecord(BaseModel):
    series_id: str | None = None
    hltv_match_id: str | None = None
    match_url: str | None = None
    match_date: date | None = None
    event_name: str | None = None
    team_1: str | None = None
    team_2: str | None = None
    target_team: str | None = None
    opponent: str | None = None
    map_name: str | None = None
    map_number: int | None = None
    demo_link: str | None = None
    source_method: Literal["manual", "scrape", "manual+scrape"]
    source_html_path: str | None = None
    scraped_at: str | None = None
    validation_status: Literal["ok", "warning"]
    validation_notes: str | None = None


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    if not isinstance(content, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return content


def load_project_config(path: Path) -> ProjectConfig:
    return ProjectConfig.model_validate(load_yaml(path))


def load_teams_config(path: Path) -> TeamsConfig:
    return TeamsConfig.model_validate(load_yaml(path))


def load_maps_config(path: Path) -> MapsConfig:
    return MapsConfig.model_validate(load_yaml(path))
