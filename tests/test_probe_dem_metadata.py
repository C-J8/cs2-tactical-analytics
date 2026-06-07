from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.parsing.probe_dem_metadata import run_probe_pipeline


def _write_config(tmp_path: Path, manifest_path: Path) -> Path:
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
dem_files_manifest_dir: {manifest_path.parent.as_posix()}
dem_files_manifest_path: {manifest_path.as_posix()}
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
    (config_dir / "maps.yaml").write_text(
        """
maps:
  - map_name: Mirage
    aliases:
      - de_mirage
      - Mirage
      - mirage
  - map_name: Nuke
    aliases:
      - de_nuke
      - Nuke
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _manifest_row(dem_path: Path, *, archive_path: str = "archive.rar", inferred_map_name: str = "unknown") -> dict[str, object]:
    return {
        "dem_file_id": dem_path.stem,
        "local_archive_id": "archive1",
        "archive_path": archive_path,
        "extracted_dir": str(dem_path.parent),
        "dem_path": str(dem_path),
        "dem_file_name": dem_path.name,
        "dem_file_size_bytes": dem_path.stat().st_size,
        "dem_sha256": "fake",
        "target_team": "Vitality",
        "assumed_map": "Mirage",
        "inferred_map_name": inferred_map_name,
        "inferred_map_number": None,
        "inference_method": "fallback",
        "parse_probe_status": "not_run",
        "notes": None,
        "created_at": "now",
    }


def test_probe_infers_from_filename(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "map1_mirage.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    updated, _, _ = run_probe_pipeline(config_path, probe_func=lambda _: None)

    assert updated.loc[0, "inferred_map_name"] == "Mirage"
    assert updated.loc[0, "inference_method"] == "filename"
    assert updated.loc[0, "parse_probe_status"] == "failed"


def test_probe_infers_from_archive_name(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "demo1.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path, archive_path="event-vitality-vs-g2-bo3-mirage.rar")]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    updated, _, _ = run_probe_pipeline(config_path, probe_func=lambda _: None)

    assert updated.loc[0, "inferred_map_name"] == "Mirage"
    assert updated.loc[0, "inference_method"] == "archive_name"
    assert updated.loc[0, "parse_probe_status"] == "failed"


def test_probe_fallback_unknown_when_parser_returns_none(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "demo1.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    updated, _, summary = run_probe_pipeline(config_path, probe_func=lambda _: None)

    assert updated.loc[0, "inferred_map_name"] == "unknown"
    assert updated.loc[0, "parse_probe_status"] == "failed"
    assert summary["total_failed"] == 1


def test_probe_dry_run_does_not_update_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "demo1.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    preview, outputs, _ = run_probe_pipeline(config_path, dry_run=True, probe_func=lambda _: "de_mirage")
    persisted = pd.read_parquet(manifest_path)

    assert preview.loc[0, "inferred_map_name"] == "Mirage"
    assert persisted.loc[0, "inferred_map_name"] == "unknown"
    assert outputs["preview_csv"].exists()


def test_probe_updates_manifest_when_parser_returns_map(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "demo1.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    updated, outputs, summary = run_probe_pipeline(config_path, probe_func=lambda _: "de_mirage")

    assert updated.loc[0, "inferred_map_name"] == "Mirage"
    assert updated.loc[0, "inference_method"] == "parser_probe"
    assert updated.loc[0, "parse_probe_status"] == "success"
    assert outputs["parquet"].exists()
    assert summary["total_success"] == 1


def test_probe_error_does_not_break_execution(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dem_files_manifest.parquet"
    dem_path = tmp_path / "demo1.dem"
    dem_path.write_bytes(b"fake")
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    def explode(_: Path) -> str:
        raise RuntimeError("nope")

    updated, _, summary = run_probe_pipeline(config_path, probe_func=explode)

    assert updated.loc[0, "parse_probe_status"] == "failed"
    assert "nope" in updated.loc[0, "probe_error_message"]
    assert summary["total_failed"] == 1
