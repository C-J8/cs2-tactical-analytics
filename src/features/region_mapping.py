from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


UNKNOWN_REGION = "UNKNOWN"
UNKNOWN_GROUP = "UNKNOWN"


def load_region_config(path: Path) -> dict:
    if not path.exists():
        return {"regions": [], "place_column_candidates": ["place"]}
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    return content if isinstance(content, dict) else {"regions": [], "place_column_candidates": ["place"]}


def build_place_lookup(config: dict) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for region in config.get("regions", []):
        region_name = str(region.get("region_name") or UNKNOWN_REGION)
        region_group = str(region.get("region_group") or UNKNOWN_GROUP)
        aliases = region.get("aliases") or []
        for alias in [region_name, *aliases]:
            lookup[normalize_place(alias)] = (region_name, region_group)
    return lookup


def choose_place_column(columns: list[str], config: dict) -> str | None:
    for candidate in config.get("place_column_candidates", ["last_place_name", "place_name", "player_last_place_name", "place"]):
        if candidate in columns:
            return candidate
    return None


def map_place_to_region(place: object, lookup: dict[str, tuple[str, str]]) -> tuple[str, str]:
    if place is None or pd.isna(place):
        return UNKNOWN_REGION, UNKNOWN_GROUP
    return lookup.get(normalize_place(str(place)), (UNKNOWN_REGION, UNKNOWN_GROUP))


def add_region_columns(df: pd.DataFrame, *, place_column: str | None, lookup: dict[str, tuple[str, str]], prefix: str = "") -> pd.DataFrame:
    mapped = df.copy()
    if place_column is None or place_column not in mapped.columns:
        mapped[f"{prefix}region_name"] = UNKNOWN_REGION
        mapped[f"{prefix}region_group"] = UNKNOWN_GROUP
        return mapped
    regions = mapped[place_column].map(lambda value: map_place_to_region(value, lookup))
    mapped[f"{prefix}region_name"] = regions.map(lambda value: value[0])
    mapped[f"{prefix}region_group"] = regions.map(lambda value: value[1])
    return mapped


def normalize_place(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())
