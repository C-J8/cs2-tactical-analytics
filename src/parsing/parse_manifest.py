from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.io import ensure_dir


PARSE_MANIFEST_COLUMNS = [
    "parse_id",
    "series_id",
    "hltv_match_id",
    "match_date",
    "event_name",
    "target_team",
    "opponent",
    "map_name",
    "map_number",
    "dem_path",
    "dem_file_name",
    "dem_file_size_bytes",
    "dem_sha256",
    "parser_backend",
    "parser_version",
    "parse_status",
    "parse_error_message",
    "parsed_at",
    "output_bronze_dir",
    "rows_rounds",
    "rows_kills",
    "rows_damages",
    "rows_shots",
    "rows_bomb",
    "rows_smokes",
    "rows_infernos",
    "rows_grenades",
    "rows_footsteps",
    "rows_ticks",
    "rows_events_total",
]


def empty_parse_manifest() -> pd.DataFrame:
    return pd.DataFrame(columns=PARSE_MANIFEST_COLUMNS)


def write_parse_manifest(df: pd.DataFrame, output_dir: Path, formats: list[str]) -> dict[str, Path]:
    ensure_dir(output_dir)
    manifest = df.copy()
    for column in PARSE_MANIFEST_COLUMNS:
        if column not in manifest.columns:
            manifest[column] = None
    manifest = manifest[PARSE_MANIFEST_COLUMNS]

    outputs: dict[str, Path] = {}
    if "csv" in formats:
        csv_path = output_dir / "parse_manifest.csv"
        manifest.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path
    if "parquet" in formats:
        parquet_path = output_dir / "parse_manifest.parquet"
        manifest.to_parquet(parquet_path, index=False)
        outputs["parquet"] = parquet_path
    return outputs
