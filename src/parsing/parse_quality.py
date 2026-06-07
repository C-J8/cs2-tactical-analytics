from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging
from src.utils.text import clean_string


PARSE_QUALITY_COLUMNS = [
    "parse_id",
    "dem_file_id",
    "dem_file_name",
    "dem_path",
    "series_id",
    "local_archive_id",
    "archive_file_name",
    "inferred_map_name",
    "target_team",
    "opponent",
    "parse_status",
    "parse_eligible",
    "is_split_segment",
    "is_merged_demo",
    "rows_rounds",
    "rows_ticks",
    "rows_kills",
    "rows_damages",
    "rows_smokes",
    "rows_grenades",
    "rows_bomb",
    "quality_status",
    "quality_notes",
    "feature_eligible",
    "created_at",
]

QUALITY_STATUSES = {
    "valid_full_map",
    "suspicious_short_demo",
    "parse_failed",
    "map_not_target",
    "split_segment_not_used",
    "missing_ticks",
    "missing_rounds",
    "unknown",
}


def run_quality_pipeline(
    config_path: Path,
    *,
    parse_manifest_path: Path | None = None,
    audit_path: Path | None = None,
    min_rounds: int = 12,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    parse_manifest_path = parse_manifest_path or project.parse_manifest_dir / "parse_manifest.parquet"
    dem_files_path = project.dem_files_manifest_path
    audit_path = audit_path or project.parse_manifest_dir.parent / "parse_audit" / "parse_audit.parquet"

    parse_manifest = read_catalog(parse_manifest_path)
    dem_files = read_catalog(dem_files_path) if dem_files_path.exists() else pd.DataFrame()
    audit = read_catalog(audit_path) if audit_path and audit_path.exists() else pd.DataFrame()
    quality = build_parse_quality(
        parse_manifest,
        dem_files,
        audit,
        target_maps=set(project.target_maps),
        min_rounds=min_rounds,
    )
    feature_eligible = quality[quality["feature_eligible"] == True].copy()  # noqa: E712

    outputs: dict[str, Path] = {}
    if dry_run:
        return quality, feature_eligible, outputs, build_summary(quality)

    parse_quality_dir = project.parse_manifest_dir.parent / "parse_quality"
    outputs.update(write_named_outputs(quality, parse_quality_dir, "parse_quality", project.output_formats, force=force))
    outputs.update(write_named_outputs(feature_eligible, project.parsed_silver_dir, "feature_eligible_demos", project.output_formats, force=force))
    return quality, feature_eligible, outputs, build_summary(quality)


def build_parse_quality(
    parse_manifest: pd.DataFrame,
    dem_files: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    target_maps: set[str],
    min_rounds: int,
) -> pd.DataFrame:
    del audit
    merged = merge_manifest_metadata(parse_manifest, dem_files)
    created_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for _, row in merged.iterrows():
        row_dict = row.to_dict()
        quality_status, quality_notes, feature_eligible = classify_quality(row_dict, target_maps=target_maps, min_rounds=min_rounds)
        rows.append(
            {
                "parse_id": clean_string(row_dict.get("parse_id")),
                "dem_file_id": clean_string(row_dict.get("dem_file_id")),
                "dem_file_name": clean_string(row_dict.get("dem_file_name")),
                "dem_path": clean_string(row_dict.get("dem_path")),
                "series_id": clean_string(row_dict.get("series_id")),
                "local_archive_id": clean_string(row_dict.get("local_archive_id")),
                "archive_file_name": clean_string(row_dict.get("archive_file_name")),
                "inferred_map_name": clean_string(row_dict.get("inferred_map_name")) or clean_string(row_dict.get("map_name")),
                "target_team": clean_string(row_dict.get("target_team")),
                "opponent": clean_string(row_dict.get("opponent")),
                "parse_status": clean_string(row_dict.get("parse_status")),
                "parse_eligible": parse_bool(row_dict.get("parse_eligible"), default=True),
                "is_split_segment": parse_bool(row_dict.get("is_split_segment"), default=False),
                "is_merged_demo": parse_bool(row_dict.get("is_merged_demo"), default=False),
                "rows_rounds": parse_int(row_dict.get("rows_rounds")),
                "rows_ticks": parse_int(row_dict.get("rows_ticks")),
                "rows_kills": parse_int(row_dict.get("rows_kills")),
                "rows_damages": parse_int(row_dict.get("rows_damages")),
                "rows_smokes": parse_int(row_dict.get("rows_smokes")),
                "rows_grenades": parse_int(row_dict.get("rows_grenades")),
                "rows_bomb": parse_int(row_dict.get("rows_bomb")),
                "quality_status": quality_status,
                "quality_notes": quality_notes,
                "feature_eligible": feature_eligible,
                "created_at": created_at,
            }
        )
    return pd.DataFrame(rows, columns=PARSE_QUALITY_COLUMNS)


def merge_manifest_metadata(parse_manifest: pd.DataFrame, dem_files: pd.DataFrame) -> pd.DataFrame:
    manifest = parse_manifest.copy()
    if manifest.empty or dem_files.empty:
        return manifest

    dem_meta = dem_files.copy()
    merge_key = choose_merge_key(manifest, dem_meta)
    if merge_key is None:
        return manifest
    if merge_key == "demo_record_id":
        dem_meta = dem_meta.rename(columns={"dem_file_id": "demo_record_id"})
    merge_columns = [
        column
        for column in [
            merge_key,
            "dem_file_id",
            "local_archive_id",
            "archive_file_name",
            "inferred_map_name",
            "parse_eligible",
            "is_split_segment",
            "is_merged_demo",
        ]
        if column in dem_meta.columns
    ]
    if merge_key not in merge_columns:
        return manifest

    merged = manifest.merge(dem_meta[merge_columns], on=merge_key, how="left", suffixes=("", "_dem"))
    if "dem_file_id" not in merged.columns and "demo_record_id" in merged.columns:
        merged["dem_file_id"] = merged["demo_record_id"]
    return merged


def choose_merge_key(parse_manifest: pd.DataFrame, dem_files: pd.DataFrame) -> str | None:
    if "demo_record_id" in parse_manifest.columns and "dem_file_id" in dem_files.columns:
        return "demo_record_id"
    if "dem_path" in parse_manifest.columns and "dem_path" in dem_files.columns:
        return "dem_path"
    if "dem_file_name" in parse_manifest.columns and "dem_file_name" in dem_files.columns:
        return "dem_file_name"
    return None


def classify_quality(row: dict[str, object], *, target_maps: set[str], min_rounds: int) -> tuple[str, str | None, bool]:
    parse_status = clean_string(row.get("parse_status")) or "unknown"
    inferred_map = clean_string(row.get("inferred_map_name")) or clean_string(row.get("map_name")) or "unknown"
    is_split_segment = parse_bool(row.get("is_split_segment"), default=False)
    rows_rounds = parse_int(row.get("rows_rounds"))
    rows_ticks = parse_int(row.get("rows_ticks"))

    if is_split_segment:
        return "split_segment_not_used", "Split segment preserved but excluded from feature inputs.", False
    if parse_status == "map_not_target" or (parse_status == "parsed" and inferred_map not in target_maps):
        return "map_not_target", f"Map {inferred_map} is outside target maps.", False
    if parse_status != "parsed":
        return "parse_failed", f"Parse status is {parse_status}.", False
    if rows_rounds is None or rows_rounds == 0:
        return "missing_rounds", "Parsed demo has no round rows.", False
    if rows_ticks is None or rows_ticks == 0:
        return "missing_ticks", "Parsed demo has no tick rows.", False
    if rows_rounds < min_rounds:
        return "suspicious_short_demo", f"Parsed demo has {rows_rounds} rounds, below min_rounds={min_rounds}.", False
    return "valid_full_map", None, True


def parse_bool(value: object, *, default: bool) -> bool:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def write_named_outputs(df: pd.DataFrame, output_dir: Path, name: str, formats: list[str], *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    if "csv" in formats:
        csv_path = output_dir / f"{name}.csv"
        write_if_allowed(df, csv_path, force=force)
        outputs[f"{name}_csv"] = csv_path
    if "parquet" in formats:
        parquet_path = output_dir / f"{name}.parquet"
        write_if_allowed(df, parquet_path, force=force)
        outputs[f"{name}_parquet"] = parquet_path
    return outputs


def write_if_allowed(df: pd.DataFrame, path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        return
    df.to_csv(path, index=False) if path.suffix == ".csv" else df.to_parquet(path, index=False)


def build_summary(quality: pd.DataFrame) -> dict[str, int]:
    if quality.empty:
        return {"total_rows": 0, "total_feature_eligible": 0}
    summary = {
        "total_rows": len(quality),
        "total_feature_eligible": int((quality["feature_eligible"] == True).sum()),  # noqa: E712
    }
    for status in sorted(QUALITY_STATUSES):
        summary[f"total_{status}"] = int((quality["quality_status"] == status).sum())
    return summary


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Parse quality summary")
    print(f"- total rows: {summary['total_rows']}")
    print(f"- total feature_eligible: {summary['total_feature_eligible']}")
    for key in sorted(key for key in summary if key.startswith("total_") and key not in {"total_rows", "total_feature_eligible"}):
        print(f"- {key.removeprefix('total_')}: {summary[key]}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build parse quality gate outputs for parsed demos.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--parse-manifest", type=Path, default=None)
    parser.add_argument("--audit", type=Path, default=None)
    parser.add_argument("--min-rounds", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, _, outputs, summary = run_quality_pipeline(
        args.config,
        parse_manifest_path=args.parse_manifest,
        audit_path=args.audit,
        min_rounds=args.min_rounds,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
