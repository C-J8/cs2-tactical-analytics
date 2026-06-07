from __future__ import annotations

import zipfile
from pathlib import Path

from src.ingestion.archive_extractor import ExtractedDemo
from src.ingestion.scan_local_archives import add_merged_split_demos, infer_metadata_from_name, infer_split_info, run_scan_pipeline


def _write_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "project.yaml"
    config_path.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-06-05"
target_maps:
  - Mirage
target_teams:
  - Vitality
output_formats:
  - csv
  - parquet
manual_seed_path: {(tmp_path / 'data/raw/manual/matches_seed.csv').as_posix()}
hltv_cache_dir: {(tmp_path / 'data/raw/hltv_pages').as_posix()}
bronze_output_dir: {(tmp_path / 'data/bronze/match_catalog_raw').as_posix()}
silver_output_dir: {(tmp_path / 'data/silver/matches_catalog').as_posix()}
demo_archive_dir: {(tmp_path / 'data/raw/demo_archives').as_posix()}
demo_output_dir: {(tmp_path / 'data/raw/demos').as_posix()}
demo_manifest_dir: {(tmp_path / 'data/bronze/demo_manifest').as_posix()}
local_archive_manifest_dir: {(tmp_path / 'data/bronze/local_archive_manifest').as_posix()}
dem_files_manifest_dir: {(tmp_path / 'data/bronze/dem_files_manifest').as_posix()}
dem_files_manifest_path: {(tmp_path / 'data/bronze/dem_files_manifest/dem_files_manifest.parquet').as_posix()}
parsed_bronze_dir: {(tmp_path / 'data/bronze/parsed_demos').as_posix()}
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
parse_manifest_dir: {(tmp_path / 'data/bronze/parse_manifest').as_posix()}
parser_backend: awpy
parse_player_props:
  - X
parse_tables:
  - ticks
parse_events: true
download_timeout_seconds: 10
download_rate_limit_seconds: 0
extract_archives: true
force_download: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_infer_metadata_from_name() -> None:
    inferred = infer_metadata_from_name(
        "iem-rio-2026-vitality-vs-g2-bo3-yhOR34cA9Po02UrfKIOtO9",
        target_team="Vitality",
    )

    assert inferred["best_of"] == "BO3"
    assert inferred["team_1"] == "Vitality"
    assert inferred["team_2"] == "G2"
    assert inferred["target_team_present"] is True


def test_scan_dry_run_generates_local_manifest_without_extracting(tmp_path: Path) -> None:
    input_dir = tmp_path / "archives"
    input_dir.mkdir()
    (input_dir / "event-vitality-vs-g2-bo3-token.rar").write_bytes(b"fake")
    (input_dir / "event-spirit-vs-vitality-bo3-token.zip").write_bytes(b"fake")
    config_path = _write_config(tmp_path)

    local_manifest, dem_manifest, outputs, summary = run_scan_pipeline(config_path, input_dir=input_dir, dry_run=True)

    assert len(local_manifest) == 2
    assert dem_manifest.empty
    assert outputs["local_archive_csv"].exists()
    assert outputs["dem_files_parquet"].exists()
    assert summary["total_archives"] == 2
    assert set(local_manifest["extract_status"]) == {"dry_run"}


def test_scan_extract_zip_generates_dem_files_manifest(tmp_path: Path) -> None:
    input_dir = tmp_path / "archives"
    input_dir.mkdir()
    zip_path = input_dir / "event-vitality-vs-g2-bo3-token.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("map1_mirage.dem", b"dem1")
        archive.writestr("map2_nuke.dem", b"dem2")
    config_path = _write_config(tmp_path)

    local_manifest, dem_manifest, outputs, summary = run_scan_pipeline(config_path, input_dir=input_dir, extract=True)

    assert local_manifest.loc[0, "extract_status"] == "extracted"
    assert len(dem_manifest) == 2
    assert set(dem_manifest["inferred_map_name"]) == {"Mirage", "Nuke"}
    assert outputs["dem_files_csv"].exists()
    assert summary["total_dem_files"] == 2


def test_scan_direct_dem_is_registered(tmp_path: Path) -> None:
    input_dir = tmp_path / "archives"
    input_dir.mkdir()
    (input_dir / "event-vitality-vs-g2-bo1-mirage.dem").write_bytes(b"fake dem")
    config_path = _write_config(tmp_path)

    local_manifest, dem_manifest, _, _ = run_scan_pipeline(config_path, input_dir=input_dir, extract=True)

    assert local_manifest.loc[0, "archive_extension"] == ".dem"
    assert len(dem_manifest) == 1
    assert Path(dem_manifest.loc[0, "dem_path"]).exists()
    assert dem_manifest.loc[0, "inferred_map_name"] == "Mirage"


def test_infer_split_info_detects_map_parts() -> None:
    split_info = infer_split_info("vitality-vs-g2-m1-mirage-p2.dem")

    assert split_info["is_split_segment"] is True
    assert split_info["split_part_number"] == 2
    assert split_info["map_number"] == 1
    assert split_info["split_group_id"] == "vitality_vs_g2_m1_mirage"


def test_scan_extract_zip_marks_split_segments_and_adds_merged_demo(tmp_path: Path) -> None:
    input_dir = tmp_path / "archives"
    input_dir.mkdir()
    zip_path = input_dir / "event-vitality-vs-g2-bo3-token.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("vitality-vs-g2-m1-mirage-p1.dem", b"part1")
        archive.writestr("vitality-vs-g2-m1-mirage-p2.dem", b"part2")
    config_path = _write_config(tmp_path)

    _, dem_manifest, _, summary = run_scan_pipeline(config_path, input_dir=input_dir, extract=True)

    assert summary["total_dem_files"] == 3
    split_rows = dem_manifest[dem_manifest["is_split_segment"] == True]  # noqa: E712
    merged_rows = dem_manifest[dem_manifest["is_merged_demo"] == True]  # noqa: E712
    assert len(split_rows) == 2
    assert len(merged_rows) == 1
    assert set(split_rows["parse_eligible"]) == {False}
    assert bool(merged_rows.iloc[0]["parse_eligible"]) is True
    assert Path(merged_rows.iloc[0]["dem_path"]).read_bytes() == b"part1part2"


def test_add_merged_split_demos_ignores_single_part(tmp_path: Path) -> None:
    part_path = tmp_path / "vitality-vs-g2-m1-mirage-p1.dem"
    part_path.write_bytes(b"part1")
    demos = [
        ExtractedDemo(
            status="extracted",
            path=part_path,
            file_size_bytes=part_path.stat().st_size,
            sha256="fake",
            extracted_at="now",
            original_file_name=part_path.name,
        )
    ]

    result = add_merged_split_demos(demos, extracted_dir=tmp_path, force=False)

    assert len(result) == 1


def test_scan_extract_calls_extractor(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "archives"
    input_dir.mkdir()
    archive_path = input_dir / "event-vitality-vs-g2-bo3-token.rar"
    archive_path.write_bytes(b"fake rar")
    config_path = _write_config(tmp_path)

    class FakeExtractor:
        def extract(self, archive_path: Path, output_dir: Path, base_name: str, *, force: bool = False):
            output_dir.mkdir(parents=True, exist_ok=True)
            dem_path = output_dir / f"{base_name}_mirage.dem"
            dem_path.write_bytes(b"fake dem")
            return type(
                "Result",
                (),
                {
                    "status": "extracted",
                    "error_message": None,
                    "demos": [
                        ExtractedDemo(
                            status="extracted",
                            path=dem_path,
                            file_size_bytes=dem_path.stat().st_size,
                            sha256="fake",
                            extracted_at="now",
                        )
                    ],
                },
            )()

    monkeypatch.setattr("src.ingestion.scan_local_archives.ArchiveExtractor", FakeExtractor)

    _, dem_manifest, _, _ = run_scan_pipeline(config_path, input_dir=input_dir, extract=True)

    assert len(dem_manifest) == 1
    assert dem_manifest.loc[0, "inferred_map_name"] == "Mirage"
