from __future__ import annotations

import re
from datetime import date

import pandas as pd

from src.config.schemas import MapsConfig, ProjectConfig, TeamsConfig
from src.ingestion.hltv_client import extract_match_id
from src.ingestion.manual_loader import EXPECTED_MANUAL_COLUMNS
from src.utils.text import clean_string, normalize_key


CATALOG_COLUMNS = [
    "series_id",
    "hltv_match_id",
    "match_url",
    "match_date",
    "event_name",
    "team_1",
    "team_2",
    "target_team",
    "opponent",
    "map_name",
    "map_number",
    "demo_link",
    "source_method",
    "source_html_path",
    "scraped_at",
    "validation_status",
    "validation_notes",
]

RAW_OPTIONAL_COLUMNS = ["source_method", "source_html_path", "scraped_at"]


def build_alias_lookup(teams_or_maps: TeamsConfig | MapsConfig) -> dict[str, str]:
    lookup: dict[str, str] = {}
    items = getattr(teams_or_maps, "teams", None) or getattr(teams_or_maps, "maps", [])
    for item in items:
        canonical = getattr(item, "team_name", None) or getattr(item, "map_name")
        lookup[normalize_key(canonical)] = canonical
        for alias in item.aliases:
            lookup[normalize_key(alias)] = canonical
    return lookup


def canonicalize_team(value: object, teams: TeamsConfig) -> str | None:
    text = clean_string(value)
    if not text:
        return None
    return build_alias_lookup(teams).get(normalize_key(text), text)


def canonicalize_map(value: object, maps: MapsConfig) -> str | None:
    text = clean_string(value)
    if not text:
        return None
    return build_alias_lookup(maps).get(normalize_key(text), text)


def generate_series_id(hltv_match_id: object) -> str | None:
    match_id = clean_string(hltv_match_id)
    if not match_id:
        return None
    digits = re.sub(r"\D+", "", match_id)
    return f"hltv_{digits or match_id}"


def normalize_manual_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in EXPECTED_MANUAL_COLUMNS + RAW_OPTIONAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized = normalized[EXPECTED_MANUAL_COLUMNS + RAW_OPTIONAL_COLUMNS]
    for column in normalized.columns:
        normalized[column] = normalized[column].map(clean_string)
    return normalized


def transform_match_catalog(
    df: pd.DataFrame,
    project: ProjectConfig,
    teams: TeamsConfig,
    maps: MapsConfig,
    *,
    source_method: str = "manual",
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=CATALOG_COLUMNS)

    records = []
    allowed_maps = {canonicalize_map(map_name, maps) for map_name in project.target_maps}
    allowed_teams = {canonicalize_team(team_name, teams) for team_name in project.target_teams}

    normalized = normalize_manual_frame(df)
    for _, row in normalized.iterrows():
        record = row.to_dict()
        if not clean_string(record.get("hltv_match_id")):
            record["hltv_match_id"] = extract_match_id(record.get("match_url"))
        record["match_url"] = clean_string(record.get("match_url"))
        record["match_date"] = _parse_date(record.get("match_date"))
        record["team_1"] = canonicalize_team(record.get("team_1"), teams)
        record["team_2"] = canonicalize_team(record.get("team_2"), teams)
        record["map_name"] = canonicalize_map(record.get("map_name"), maps)
        record["map_number"] = _parse_int(record.get("map_number"))
        record["series_id"] = generate_series_id(record.get("hltv_match_id"))
        record["target_team"] = identify_target_team(record.get("team_1"), record.get("team_2"), allowed_teams)
        record["opponent"] = identify_opponent(record.get("team_1"), record.get("team_2"), record.get("target_team"))
        record["source_method"] = clean_string(record.get("source_method")) or source_method
        record.setdefault("source_html_path", None)
        record.setdefault("scraped_at", None)
        records.append(record)

    catalog = pd.DataFrame(records)
    catalog = _apply_filters(catalog, project, allowed_maps, allowed_teams)
    catalog = _deduplicate(catalog)
    catalog = _validate(catalog, project, allowed_maps, allowed_teams)
    return catalog[CATALOG_COLUMNS]


def identify_target_team(team_1: object, team_2: object, allowed_teams: set[str | None]) -> str | None:
    team_1 = clean_string(team_1)
    team_2 = clean_string(team_2)
    if team_1 in allowed_teams:
        return team_1
    if team_2 in allowed_teams:
        return team_2
    return None


def identify_opponent(team_1: object, team_2: object, target_team: object) -> str | None:
    team_1 = clean_string(team_1)
    team_2 = clean_string(team_2)
    target_team = clean_string(target_team)
    if not target_team:
        return None
    if team_1 == target_team and team_2 != target_team:
        return team_2
    if team_2 == target_team and team_1 != target_team:
        return team_1
    return None


def find_duplicate_keys(df: pd.DataFrame) -> pd.Series:
    keys = ["hltv_match_id", "map_name", "map_number"]
    complete_keys = df[keys].notna().all(axis=1)
    return complete_keys & df.duplicated(keys, keep=False)


def _parse_date(value: object) -> date | None:
    text = clean_string(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _parse_int(value: object) -> int | None:
    text = clean_string(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _apply_filters(
    catalog: pd.DataFrame,
    project: ProjectConfig,
    allowed_maps: set[str | None],
    allowed_teams: set[str | None],
) -> pd.DataFrame:
    keep_map = catalog["map_name"].isna() | catalog["map_name"].isin(allowed_maps)
    keep_team = catalog["target_team"].isna() | catalog["target_team"].isin(allowed_teams)

    def date_in_range(value: object) -> bool:
        if value is None or pd.isna(value):
            return True
        return project.date_start <= value <= project.date_end

    keep_date = catalog["match_date"].map(date_in_range)
    return catalog[keep_map & keep_team & keep_date].copy()


def _deduplicate(catalog: pd.DataFrame) -> pd.DataFrame:
    keys = ["hltv_match_id", "map_name", "map_number"]
    complete_keys = catalog[keys].notna().all(axis=1)
    deduped_complete = catalog[complete_keys].drop_duplicates(keys, keep="first")
    incomplete = catalog[~complete_keys]
    return pd.concat([deduped_complete, incomplete], ignore_index=True)


def _validate(
    catalog: pd.DataFrame,
    project: ProjectConfig,
    allowed_maps: set[str | None],
    allowed_teams: set[str | None],
) -> pd.DataFrame:
    duplicate_flags = find_duplicate_keys(catalog)
    statuses = []
    notes = []
    for idx, row in catalog.iterrows():
        row_notes: list[str] = []
        if not clean_string(row.get("match_url")) and not clean_string(row.get("hltv_match_id")):
            row_notes.append("missing match_url and hltv_match_id")
        if row.get("match_date") is None:
            row_notes.append("missing or invalid match_date")
        if clean_string(row.get("map_name")) not in allowed_maps:
            row_notes.append("missing or unsupported map_name")
        if clean_string(row.get("target_team")) not in allowed_teams:
            row_notes.append("target_team not found in configured teams")
        if not clean_string(row.get("opponent")):
            row_notes.append("opponent could not be inferred")
        if clean_string(row.get("opponent")) == clean_string(row.get("target_team")):
            row_notes.append("opponent equals target_team")
        if pd.isna(row.get("map_number")):
            row_notes.append("missing or invalid map_number")
        if duplicate_flags.loc[idx]:
            row_notes.append("duplicate hltv_match_id + map_name + map_number")

        statuses.append("warning" if row_notes else "ok")
        notes.append("; ".join(row_notes) if row_notes else None)

    catalog = catalog.copy()
    catalog["validation_status"] = statuses
    catalog["validation_notes"] = notes
    return catalog
