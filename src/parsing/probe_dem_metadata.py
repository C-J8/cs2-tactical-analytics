from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from src.config.schemas import load_maps_config, load_project_config
from src.ingestion.scan_local_archives import infer_map_name
from src.ingestion.validators import canonicalize_map
from src.utils.io import read_catalog
from src.utils.logging import configure_logging
from src.utils.text import clean_string

PROBE_COLUMNS = [
    "probe_error_message",
    "previous_inferred_map_name",
    "probed_at",
]


def run_probe_pipeline(
    config_path: Path,
    *,
    manifest_path: Path | None = None,
    limit: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    backend: str = "awpy",
    include_known: bool = False,
    probe_func: Callable[[Path], str | None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    if backend != "awpy":
        raise ValueError(f"Unsupported probe backend: {backend}")
    maps = load_maps_config(config_path.parent / "maps.yaml")
    manifest_path = manifest_path or project.dem_files_manifest_path
    manifest = read_catalog(manifest_path)
    manifest = ensure_probe_columns(manifest)
    selected = select_probe_rows(manifest, include_known=include_known)
    if limit is not None:
        selected = selected.head(limit)

    probe_func = probe_func or probe_map_with_demoparser
    updated = manifest.copy()
    preview_rows = []
    for idx, row in selected.iterrows():
        result = probe_row(row.to_dict(), maps=maps, probe_func=probe_func, force=force)
        preview_rows.append(result)
        if not dry_run:
            for key, value in result.items():
                updated.loc[idx, key] = value

    outputs: dict[str, Path] = {}
    if dry_run:
        preview = pd.DataFrame(preview_rows)
        preview_path = project.dem_files_manifest_dir / "dem_files_manifest_probe_preview.csv"
        project.dem_files_manifest_dir.mkdir(parents=True, exist_ok=True)
        preview.to_csv(preview_path, index=False)
        outputs["preview_csv"] = preview_path
    else:
        outputs = write_dem_files_manifest(updated, project.dem_files_manifest_dir, project.output_formats)

    return updated if not dry_run else pd.DataFrame(preview_rows), outputs, build_summary(pd.DataFrame(preview_rows))


def ensure_probe_columns(manifest: pd.DataFrame) -> pd.DataFrame:
    updated = manifest.copy()
    for column in PROBE_COLUMNS:
        if column not in updated.columns:
            updated[column] = None
    return updated


def select_probe_rows(manifest: pd.DataFrame, *, include_known: bool) -> pd.DataFrame:
    if manifest.empty or "dem_path" not in manifest.columns:
        return pd.DataFrame()

    def should_probe(row: pd.Series) -> bool:
        dem_path = clean_string(row.get("dem_path"))
        if not dem_path or not Path(dem_path).exists():
            return False
        current = clean_string(row.get("inferred_map_name"))
        return include_known or current is None or current.lower() == "unknown"

    return manifest[manifest.apply(should_probe, axis=1)].copy()


def probe_row(
    row: dict[str, object],
    *,
    maps,
    probe_func: Callable[[Path], str | None],
    force: bool,
) -> dict[str, object]:
    previous = clean_string(row.get("inferred_map_name")) or "unknown"
    dem_path = Path(str(row.get("dem_path")))
    result = {
        "dem_file_id": row.get("dem_file_id"),
        "dem_path": str(dem_path),
        "previous_inferred_map_name": previous,
        "probe_error_message": None,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        probed = probe_func(dem_path)
        canonical = canonicalize_map(probed, maps) if probed else None
        if canonical:
            return {
                **result,
                "inferred_map_name": canonical,
                "inference_method": "parser_probe",
                "parse_probe_status": "success",
                "notes": clean_string(row.get("notes")),
            }
    except Exception as exc:
        filename_map, _, filename_notes = infer_map_name(dem_path.name, "")
        if filename_map != "unknown":
            return {
                **result,
                "inferred_map_name": canonicalize_map(filename_map, maps) or filename_map,
                "inference_method": "filename",
                "parse_probe_status": "failed",
                "probe_error_message": str(exc),
                "notes": merge_notes(row.get("notes"), filename_notes + ["parser probe failed; used filename fallback"]),
            }
        archive_path = clean_string(row.get("archive_path")) or ""
        archive_file_name = Path(archive_path).name if archive_path else ""
        archive_map, _, archive_notes = infer_map_name("", archive_file_name)
        if archive_map != "unknown":
            return {
                **result,
                "inferred_map_name": canonicalize_map(archive_map, maps) or archive_map,
                "inference_method": "archive_name",
                "parse_probe_status": "failed",
                "probe_error_message": str(exc),
                "notes": merge_notes(row.get("notes"), archive_notes + ["parser probe failed; used archive_name fallback"]),
            }
        return {
            **result,
            "inferred_map_name": previous if previous != "unknown" and not force else "unknown",
            "inference_method": "unknown",
            "parse_probe_status": "failed",
            "probe_error_message": str(exc),
            "notes": merge_notes(row.get("notes"), ["parser probe failed"]),
        }

    filename_map, _, filename_notes = infer_map_name(dem_path.name, "")
    if filename_map != "unknown":
        return {
            **result,
            "inferred_map_name": canonicalize_map(filename_map, maps) or filename_map,
            "inference_method": "filename",
            "parse_probe_status": "failed",
            "notes": merge_notes(row.get("notes"), filename_notes + ["parser probe returned no map; used filename fallback"]),
        }

    archive_path = clean_string(row.get("archive_path")) or ""
    archive_file_name = Path(archive_path).name if archive_path else ""
    archive_map, _, archive_notes = infer_map_name("", archive_file_name)
    if archive_map != "unknown":
        return {
            **result,
            "inferred_map_name": canonicalize_map(archive_map, maps) or archive_map,
            "inference_method": "archive_name",
            "parse_probe_status": "failed",
            "notes": merge_notes(row.get("notes"), archive_notes + ["parser probe returned no map; used archive_name fallback"]),
        }

    return {
        **result,
        "inferred_map_name": previous if previous != "unknown" and not force else "unknown",
        "inference_method": "unknown",
        "parse_probe_status": "failed",
        "notes": merge_notes(row.get("notes"), ["could not infer map_name"]),
    }


def probe_map_with_demoparser(dem_path: Path) -> str | None:
    from demoparser2 import DemoParser

    parser = DemoParser(str(dem_path))
    header = parser.parse_header()
    if isinstance(header, dict):
        return clean_string(header.get("map_name"))
    return None


def merge_notes(existing: object, new_notes: list[str]) -> str | None:
    notes = []
    existing_text = clean_string(existing)
    if existing_text:
        notes.append(existing_text)
    notes.extend(note for note in new_notes if note)
    return "; ".join(dict.fromkeys(notes)) if notes else None


def write_dem_files_manifest(df: pd.DataFrame, output_dir: Path, formats: list[str]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    if "csv" in formats:
        csv_path = output_dir / "dem_files_manifest.csv"
        df.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path
    if "parquet" in formats:
        parquet_path = output_dir / "dem_files_manifest.parquet"
        df.to_parquet(parquet_path, index=False)
        outputs["parquet"] = parquet_path
    return outputs


def build_summary(results: pd.DataFrame) -> dict[str, int]:
    if results.empty:
        return {"total_probed": 0, "total_success": 0, "total_failed": 0}
    return {
        "total_probed": len(results),
        "total_success": int((results["parse_probe_status"] == "success").sum()),
        "total_failed": int((results["parse_probe_status"] == "failed").sum()),
    }


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("DEM metadata probe summary")
    print(f"- total probed: {summary['total_probed']}")
    print(f"- total success: {summary['total_success']}")
    print(f"- total failed: {summary['total_failed']}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe DEM metadata to infer map names without full parsing.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backend", default="awpy")
    parser.add_argument("--include-known", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_probe_pipeline(
        args.config,
        manifest_path=args.manifest,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
        backend=args.backend,
        include_known=args.include_known,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
