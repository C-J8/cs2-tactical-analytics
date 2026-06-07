from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config.schemas import ProjectConfig, load_project_config
from src.ingestion.archive_extractor import ArchiveExtractor, ExtractedDemo
from src.ingestion.demo_downloader import sha256_file
from src.utils.io import ensure_dir
from src.utils.logging import configure_logging
from src.utils.text import safe_slug

ARCHIVE_EXTENSIONS = {".rar", ".zip", ".dem"}
MAP_NAMES = {"mirage", "inferno", "nuke", "overpass", "ancient", "anubis", "dust2", "train", "vertigo"}

LOCAL_ARCHIVE_COLUMNS = [
    "local_archive_id",
    "archive_path",
    "archive_file_name",
    "archive_extension",
    "archive_file_size_bytes",
    "archive_sha256",
    "target_team",
    "assumed_map",
    "inferred_event_name",
    "inferred_team_1",
    "inferred_team_2",
    "inferred_best_of",
    "target_team_present",
    "scan_status",
    "notes",
    "scanned_at",
    "extract_status",
    "extracted_dir",
    "extracted_dem_count",
    "error_message",
]

DEM_FILES_COLUMNS = [
    "dem_file_id",
    "local_archive_id",
    "archive_path",
    "extracted_dir",
    "dem_path",
    "dem_file_name",
    "original_dem_file_name",
    "dem_file_size_bytes",
    "dem_sha256",
    "target_team",
    "assumed_map",
    "inferred_map_name",
    "inferred_map_number",
    "inference_method",
    "is_split_segment",
    "split_part_number",
    "split_group_id",
    "is_merged_demo",
    "merge_status",
    "merge_error_message",
    "parse_eligible",
    "exclusion_reason",
    "parse_probe_status",
    "notes",
    "created_at",
]


def run_scan_pipeline(
    config_path: Path,
    *,
    input_dir: Path | None = None,
    target_team: str | None = None,
    assumed_map: str | None = None,
    extract: bool = False,
    force: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    assumed_map = assumed_map or project.target_maps[0]
    input_dir = input_dir or project.demo_archive_dir / target_team / assumed_map

    archives = scan_archive_files(input_dir)
    if limit is not None:
        archives = archives[:limit]

    extractor = ArchiveExtractor()
    local_rows: list[dict[str, object]] = []
    dem_rows: list[dict[str, object]] = []
    for archive_path in archives:
        local_row, extracted_demos = process_archive(
            archive_path,
            project,
            target_team=target_team,
            assumed_map=assumed_map,
            extractor=extractor,
            extract=extract and not dry_run,
            force=force,
            dry_run=dry_run,
        )
        local_rows.append(local_row)
        extracted_demos = add_merged_split_demos(extracted_demos, extracted_dir=Path(str(local_row["extracted_dir"])), force=force)
        for demo in extracted_demos:
            dem_rows.append(build_dem_file_row(local_row, demo, target_team=target_team, assumed_map=assumed_map))

    local_manifest = pd.DataFrame(local_rows, columns=LOCAL_ARCHIVE_COLUMNS)
    dem_manifest = pd.DataFrame(dem_rows, columns=DEM_FILES_COLUMNS)
    outputs = {}
    outputs.update({f"local_archive_{k}": v for k, v in write_manifest(local_manifest, project.local_archive_manifest_dir, "local_archive_manifest", project.output_formats).items()})
    outputs.update({f"dem_files_{k}": v for k, v in write_manifest(dem_manifest, project.dem_files_manifest_dir, "dem_files_manifest", project.output_formats).items()})
    return local_manifest, dem_manifest, outputs, build_summary(local_manifest, dem_manifest)


def scan_archive_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS],
        key=lambda path: path.name.lower(),
    )


def process_archive(
    archive_path: Path,
    project: ProjectConfig,
    *,
    target_team: str,
    assumed_map: str,
    extractor: ArchiveExtractor,
    extract: bool,
    force: bool,
    dry_run: bool,
) -> tuple[dict[str, object], list[ExtractedDemo]]:
    inferred = infer_metadata_from_name(archive_path.stem, target_team=target_team)
    local_archive_id = safe_slug(archive_path.stem, fallback="archive")
    extracted_dir = project.demo_output_dir / target_team / local_archive_id
    notes = inferred["notes"]
    extracted_demos: list[ExtractedDemo] = []
    extract_status = "dry_run" if dry_run else "not_needed"
    error_message = None

    if extract:
        result = extractor.extract(archive_path, extracted_dir, local_archive_id, force=force)
        extract_status = result.status
        error_message = result.error_message
        extracted_demos = result.demos

    row = {
        "local_archive_id": local_archive_id,
        "archive_path": str(archive_path),
        "archive_file_name": archive_path.name,
        "archive_extension": archive_path.suffix.lower(),
        "archive_file_size_bytes": archive_path.stat().st_size,
        "archive_sha256": sha256_file(archive_path),
        "target_team": target_team,
        "assumed_map": assumed_map,
        "inferred_event_name": inferred["event_name"],
        "inferred_team_1": inferred["team_1"],
        "inferred_team_2": inferred["team_2"],
        "inferred_best_of": inferred["best_of"],
        "target_team_present": inferred["target_team_present"],
        "scan_status": "ok",
        "notes": "; ".join(notes) if notes else None,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "extract_status": extract_status,
        "extracted_dir": str(extracted_dir) if extract or dry_run else None,
        "extracted_dem_count": len(extracted_demos),
        "error_message": error_message,
    }
    return row, extracted_demos


def infer_metadata_from_name(stem: str, *, target_team: str) -> dict[str, object]:
    normalized = stem.lower()
    target = safe_slug(target_team).replace("_", "-")
    notes: list[str] = []
    best_of_match = re.search(r"(?:^|-)(bo\d+)(?:-|$)", normalized)
    best_of = best_of_match.group(1).upper() if best_of_match else "unknown"
    if best_of == "unknown":
        notes.append("could not infer best_of")

    event_name = "unknown"
    team_1 = "unknown"
    team_2 = "unknown"
    if "-vs-" in normalized:
        left, right = normalized.split("-vs-", 1)
        right_parts = right.split("-")
        bo_index = next((idx for idx, part in enumerate(right_parts) if re.fullmatch(r"bo\d+", part)), len(right_parts))
        team_2_slug = "-".join(right_parts[:bo_index])
        left_parts = left.split("-")
        team_1_slug = infer_team_slug(left_parts, target_slug=target)
        event_slug = left[: -len(team_1_slug)].strip("-") if team_1_slug != "unknown" and left.endswith(team_1_slug) else "unknown"
        event_name = prettify_slug(event_slug)
        team_1 = prettify_slug(team_1_slug)
        team_2 = prettify_slug(team_2_slug)
    else:
        notes.append("could not infer teams")

    if event_name == "unknown":
        notes.append("could not infer event_name")
    target_present = target in {safe_slug(team_1).replace("_", "-"), safe_slug(team_2).replace("_", "-")} or target in normalized
    return {
        "event_name": event_name,
        "team_1": team_1,
        "team_2": team_2,
        "best_of": best_of,
        "target_team_present": target_present,
        "notes": notes,
    }


def infer_team_slug(left_parts: list[str], *, target_slug: str) -> str:
    if not left_parts:
        return "unknown"
    if left_parts[-1] == target_slug:
        return target_slug
    if len(left_parts) >= 2 and "-".join(left_parts[-2:]) in {"the-mongolz", "natus-vincere", "gamerlegion"}:
        return "-".join(left_parts[-2:])
    return left_parts[-1]


def prettify_slug(value: str) -> str:
    if not value or value == "unknown":
        return "unknown"
    return " ".join(part.capitalize() if part not in {"g2", "b8"} else part.upper() for part in value.split("-"))


def build_dem_file_row(local_row: dict[str, object], demo: ExtractedDemo, *, target_team: str, assumed_map: str) -> dict[str, object]:
    assert demo.path is not None
    original_name = demo.original_file_name or demo.path.name
    split_info = infer_split_info(original_name)
    inferred_map, method, notes = infer_map_name(original_name, str(local_row["archive_file_name"]))
    if inferred_map == "unknown":
        inferred_map, method, notes = infer_map_name(demo.path.name, str(local_row["archive_file_name"]))
    is_split_segment = split_info["is_split_segment"] and not demo.is_merged
    parse_eligible = not is_split_segment
    exclusion_reason = "split_segment_merged" if is_split_segment else None
    return {
        "dem_file_id": safe_slug(f"{local_row['local_archive_id']}_{demo.path.stem}", fallback="dem"),
        "local_archive_id": local_row["local_archive_id"],
        "archive_path": local_row["archive_path"],
        "extracted_dir": local_row["extracted_dir"],
        "dem_path": str(demo.path),
        "dem_file_name": demo.path.name,
        "original_dem_file_name": original_name,
        "dem_file_size_bytes": demo.file_size_bytes,
        "dem_sha256": demo.sha256,
        "target_team": target_team,
        "assumed_map": assumed_map,
        "inferred_map_name": inferred_map,
        "inferred_map_number": split_info["map_number"] or infer_map_number(original_name) or infer_map_number(demo.path.name),
        "inference_method": method,
        "is_split_segment": is_split_segment,
        "split_part_number": split_info["split_part_number"] if is_split_segment else demo.split_part_number,
        "split_group_id": demo.split_group_id or split_info["split_group_id"],
        "is_merged_demo": demo.is_merged,
        "merge_status": "merged" if demo.is_merged else None,
        "merge_error_message": demo.error_message,
        "parse_eligible": parse_eligible,
        "exclusion_reason": exclusion_reason,
        "parse_probe_status": "not_run",
        "notes": "; ".join(notes) if notes else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def infer_map_name(dem_file_name: str, archive_file_name: str) -> tuple[str, str, list[str]]:
    for source_name, method in [(dem_file_name, "dem_file_name"), (archive_file_name, "archive_file_name")]:
        key = safe_slug(source_name).replace("_", "-")
        for map_name in MAP_NAMES:
            if map_name in key:
                return canonical_map_name(map_name), method, []
    return "unknown", "fallback", ["could not infer map_name"]


def canonical_map_name(value: str) -> str:
    return "Dust2" if value == "dust2" else value.capitalize()


def infer_map_number(dem_file_name: str) -> int | None:
    match = re.search(r"(?:map|dem|m)(\d+)", dem_file_name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def infer_split_info(file_name: str) -> dict[str, object]:
    stem = Path(file_name).stem.lower()
    match = re.search(r"(?P<base>.+?)[-_]m(?P<map_number>\d+)[-_](?P<map_name>[a-z0-9]+)[-_]p(?P<part>\d+)$", stem)
    if not match:
        return {
            "is_split_segment": False,
            "split_part_number": None,
            "split_group_id": None,
            "map_number": infer_map_number(file_name),
        }
    group_base = match.group("base")
    map_number = int(match.group("map_number"))
    map_name = match.group("map_name")
    return {
        "is_split_segment": True,
        "split_part_number": int(match.group("part")),
        "split_group_id": safe_slug(f"{group_base}_m{map_number}_{map_name}", fallback="split_group"),
        "map_number": map_number,
    }


def add_merged_split_demos(extracted_demos: list[ExtractedDemo], *, extracted_dir: Path, force: bool) -> list[ExtractedDemo]:
    groups: dict[str, list[ExtractedDemo]] = {}
    for demo in extracted_demos:
        source_name = demo.original_file_name or (demo.path.name if demo.path else "")
        split_info = infer_split_info(source_name)
        if split_info["is_split_segment"]:
            demo.split_group_id = str(split_info["split_group_id"])
            demo.split_part_number = int(split_info["split_part_number"])
            groups.setdefault(demo.split_group_id, []).append(demo)

    merged_demos: list[ExtractedDemo] = []
    for split_group_id, parts in groups.items():
        if len(parts) < 2:
            continue
        merged_demos.append(merge_split_group(split_group_id, parts, extracted_dir=extracted_dir, force=force))
    return extracted_demos + merged_demos


def merge_split_group(split_group_id: str, parts: list[ExtractedDemo], *, extracted_dir: Path, force: bool) -> ExtractedDemo:
    sorted_parts = sorted(parts, key=lambda demo: demo.split_part_number or 0)
    output_path = extracted_dir / f"{split_group_id}_merged.dem"
    if output_path.exists() and not force:
        return ExtractedDemo(
            status="skipped_existing",
            path=output_path,
            file_size_bytes=output_path.stat().st_size,
            sha256=sha256_file(output_path),
            extracted_at=None,
            original_file_name=f"{split_group_id}_merged.dem",
            is_merged=True,
            split_group_id=split_group_id,
        )
    try:
        with output_path.open("wb") as target:
            for part in sorted_parts:
                if part.path is None:
                    continue
                with part.path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
    except OSError as exc:
        return ExtractedDemo(
            status="failed",
            path=output_path,
            file_size_bytes=None,
            sha256=None,
            extracted_at=None,
            error_message=str(exc),
            original_file_name=f"{split_group_id}_merged.dem",
            is_merged=True,
            split_group_id=split_group_id,
        )
    return ExtractedDemo(
        status="merged",
        path=output_path,
        file_size_bytes=output_path.stat().st_size,
        sha256=sha256_file(output_path),
        extracted_at=datetime.now(timezone.utc).isoformat(),
        original_file_name=f"{split_group_id}_merged.dem",
        is_merged=True,
        split_group_id=split_group_id,
    )


def write_manifest(df: pd.DataFrame, output_dir: Path, name: str, formats: list[str]) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    if "csv" in formats:
        csv_path = output_dir / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path
    if "parquet" in formats:
        parquet_path = output_dir / f"{name}.parquet"
        df.to_parquet(parquet_path, index=False)
        outputs["parquet"] = parquet_path
    return outputs


def build_summary(local_manifest: pd.DataFrame, dem_manifest: pd.DataFrame) -> dict[str, int]:
    return {
        "total_archives": len(local_manifest),
        "total_extracted_archives": int(local_manifest["extract_status"].isin(["extracted", "not_needed"]).sum()) if not local_manifest.empty else 0,
        "total_failed_extract": int((local_manifest["extract_status"] == "failed").sum()) if not local_manifest.empty else 0,
        "total_dem_files": len(dem_manifest),
    }


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Local archive scan summary")
    print(f"- total archives: {summary['total_archives']}")
    print(f"- total archives extracted/registered: {summary['total_extracted_archives']}")
    print(f"- total extraction failures: {summary['total_failed_extract']}")
    print(f"- total dem files registered: {summary['total_dem_files']}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan local HLTV demo archives and build archive/DEM manifests.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--assumed-map", default=None)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, _, outputs, summary = run_scan_pipeline(
        args.config,
        input_dir=args.input_dir,
        target_team=args.target_team,
        assumed_map=args.assumed_map,
        extract=args.extract,
        force=args.force,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
