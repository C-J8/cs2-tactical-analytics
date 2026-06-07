from __future__ import annotations

from pathlib import Path

import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_catalog(df: pd.DataFrame, output_dir: Path, formats: list[str]) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}

    if "csv" in formats:
        csv_path = output_dir / "matches_catalog.csv"
        df.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path

    if "parquet" in formats:
        parquet_path = output_dir / "matches_catalog.parquet"
        df.to_parquet(parquet_path, index=False)
        outputs["parquet"] = parquet_path

    return outputs


def write_bronze_snapshot(df: pd.DataFrame, output_dir: Path) -> Path:
    ensure_dir(output_dir)
    path = output_dir / "match_catalog_raw.csv"
    df.to_csv(path, index=False)
    return path


def read_catalog(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Catalog not found: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype="string", keep_default_na=False)
    raise ValueError(f"Unsupported catalog format: {path}")


def default_catalog_path(silver_output_dir: Path) -> Path:
    parquet_path = silver_output_dir / "matches_catalog.parquet"
    if parquet_path.exists():
        return parquet_path
    return silver_output_dir / "matches_catalog.csv"


def write_manifest(df: pd.DataFrame, output_dir: Path, formats: list[str]) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}

    if "csv" in formats:
        csv_path = output_dir / "demo_manifest.csv"
        df.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path

    if "parquet" in formats:
        parquet_path = output_dir / "demo_manifest.parquet"
        df.to_parquet(parquet_path, index=False)
        outputs["parquet"] = parquet_path

    return outputs
