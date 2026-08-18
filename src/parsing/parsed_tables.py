from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from src.utils.io import ensure_dir
from src.utils.text import clean_string


TRACE_COLUMNS = [
    "series_id",
    "hltv_match_id",
    "map_name",
    "map_number",
    "target_team",
    "opponent",
    "dem_path",
    "source_parse_id",
]


def add_trace_columns(df: pd.DataFrame, row: dict[str, object], parse_id: str) -> pd.DataFrame:
    traced = df.copy()
    traced["series_id"] = clean_string(row.get("series_id"))
    traced["hltv_match_id"] = clean_string(row.get("hltv_match_id"))
    traced["map_name"] = clean_string(row.get("map_name"))
    traced["map_number"] = clean_string(row.get("map_number"))
    traced["target_team"] = clean_string(row.get("target_team"))
    traced["opponent"] = clean_string(row.get("opponent"))
    traced["dem_path"] = clean_string(row.get("dem_path"))
    traced["source_parse_id"] = parse_id
    return traced


def write_bronze_tables(
    tables: dict[str, pd.DataFrame],
    events: dict[str, pd.DataFrame],
    output_dir: Path,
) -> dict[str, int]:
    ensure_dir(output_dir)
    row_counts: dict[str, int] = {}
    for table_name, df in tables.items():
        frame = ensure_dataframe(df)
        frame.to_parquet(output_dir / f"{table_name}.parquet", index=False)
        row_counts[table_name] = len(frame)

    if events:
        events_dir = ensure_dir(output_dir / "events")
        total_events = 0
        for event_name, df in events.items():
            frame = ensure_dataframe(df)
            frame.to_parquet(events_dir / f"{event_name}.parquet", index=False)
            total_events += len(frame)
        row_counts["events_total"] = total_events
    else:
        row_counts["events_total"] = 0
    return row_counts


def write_silver_tables(
    tables: dict[str, pd.DataFrame],
    row: dict[str, object],
    parse_id: str,
    output_dir: Path,
) -> dict[str, pd.DataFrame]:
    ensure_dir(output_dir)
    traced_tables = {
        table_name: add_trace_columns(ensure_dataframe(df), row, parse_id)
        for table_name, df in tables.items()
    }
    for table_name, traced in traced_tables.items():
        path = output_dir / f"{table_name}.parquet"
        if path.exists():
            upsert_silver_table(path, traced, parse_ids={str(parse_id)})
        else:
            traced = deduplicate_silver_table(traced)
            traced.to_parquet(path, index=False)
    return traced_tables


def upsert_silver_table(path: Path, new_rows: pd.DataFrame, *, parse_ids: set[str]) -> pd.DataFrame:
    incoming = normalize_trace_columns(ensure_dataframe(new_rows))
    if "source_parse_id" not in incoming.columns:
        raise ValueError(f"Cannot safely upsert silver rows without source_parse_id: {path}")
    if path.exists():
        schema = pl.scan_parquet(path).collect_schema()
        if "source_parse_id" not in schema.names():
            raise ValueError(f"Cannot safely upsert silver table without source_parse_id: {path}")
        temp_new = path.with_suffix(".new_scope.parquet")
        temp_out = path.with_suffix(".upsert_tmp.parquet")
        deduplicate_silver_table(incoming).to_parquet(temp_new, index=False)
        try:
            pl.concat(
                [
                    pl.scan_parquet(path).filter(~pl.col("source_parse_id").cast(pl.Utf8).is_in(list(parse_ids))),
                    pl.scan_parquet(temp_new),
                ],
                how="diagonal_relaxed",
            ).sink_parquet(temp_out)
            temp_out.replace(path)
        finally:
            if temp_new.exists():
                temp_new.unlink()
            if temp_out.exists():
                temp_out.unlink()
        return incoming
    incoming = deduplicate_silver_table(incoming)
    ensure_dir(path.parent)
    incoming.to_parquet(path, index=False)
    return incoming


def deduplicate_silver_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    stable_keys = [column for column in ["source_parse_id", "round_num", "tick", "steamid", "event", "entity_id"] if column in df.columns]
    if not stable_keys:
        return df.drop_duplicates().reset_index(drop=True)
    return df.drop_duplicates(subset=stable_keys, keep="last").reset_index(drop=True)


def normalize_trace_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in TRACE_COLUMNS:
        if column in normalized.columns:
            normalized[column] = normalized[column].map(clean_string)
    return normalized


def ensure_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    return df.copy()


def bronze_output_dir(base_dir: Path, row: dict[str, object]) -> Path:
    return base_dir / str(row.get("target_team") or "unknown_team") / str(row.get("map_name") or "unknown_map") / str(row.get("series_id") or "unknown_series")
