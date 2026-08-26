from __future__ import annotations

from pathlib import Path

import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_table(path: Path, *, csv_dtype: str | None = None, keep_default_na: bool = True) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Table not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path, dtype=csv_dtype, keep_default_na=keep_default_na)
    raise ValueError(f"Unsupported table format: {path}")


def read_optional_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return read_table(path)


def read_table_pair(path_without_suffix: Path) -> pd.DataFrame:
    parquet_path = path_without_suffix.with_suffix(".parquet")
    csv_path = path_without_suffix.with_suffix(".csv")
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    raise FileNotFoundError(f"Table not found: {parquet_path} or {csv_path}")


def write_dataframe_outputs(
    frames: dict[str, pd.DataFrame],
    output_dir: Path,
    *,
    force: bool,
    formats: tuple[str, ...] = ("csv", "parquet"),
) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name, frame in frames.items():
        for suffix in formats:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                if suffix == "csv":
                    frame.to_csv(path, index=False)
                elif suffix == "parquet":
                    frame.to_parquet(path, index=False)
                else:
                    raise ValueError(f"Unsupported output format: {suffix}")
            outputs[f"{name}_{suffix}"] = path
    return outputs


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
