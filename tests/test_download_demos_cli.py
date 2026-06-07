from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

from src.ingestion.download_demos import run_download_pipeline
from src.utils.io import read_catalog


def _catalog_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series_id": "hltv_42",
                "hltv_match_id": "42",
                "match_url": "https://www.hltv.org/matches/42/example",
                "match_date": "2026-01-01",
                "event_name": "Example",
                "team_1": "Vitality",
                "team_2": "NAVI",
                "target_team": "Vitality",
                "opponent": "NAVI",
                "map_name": "Mirage",
                "map_number": 1,
                "demo_link": "https://example.test/demo.zip",
                "source_method": "manual",
                "validation_status": "ok",
                "validation_notes": "",
            },
            {
                "series_id": "hltv_43",
                "hltv_match_id": "43",
                "match_url": "https://www.hltv.org/matches/43/example",
                "match_date": "2026-01-02",
                "event_name": "Example",
                "team_1": "Vitality",
                "team_2": "G2",
                "target_team": "Vitality",
                "opponent": "G2",
                "map_name": "Mirage",
                "map_number": 1,
                "demo_link": "",
                "source_method": "manual",
                "validation_status": "ok",
                "validation_notes": "",
            },
        ]
    )


def _write_config(tmp_path: Path, catalog_dir: Path) -> Path:
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
rate_limit_seconds: 0
cache_enabled: true
manual_seed_path: {(tmp_path / 'data/raw/manual/matches_seed.csv').as_posix()}
hltv_cache_dir: {(tmp_path / 'data/raw/hltv_pages').as_posix()}
bronze_output_dir: {(tmp_path / 'data/bronze/match_catalog_raw').as_posix()}
silver_output_dir: {catalog_dir.as_posix()}
demo_archive_dir: {(tmp_path / 'data/raw/demo_archives').as_posix()}
demo_output_dir: {(tmp_path / 'data/raw/demos').as_posix()}
demo_manifest_dir: {(tmp_path / 'data/bronze/demo_manifest').as_posix()}
download_timeout_seconds: 10
download_rate_limit_seconds: 0
max_downloads_per_run: null
extract_archives: true
force_download: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_read_catalog_csv_and_parquet(tmp_path: Path) -> None:
    df = _catalog_frame()
    csv_path = tmp_path / "catalog.csv"
    parquet_path = tmp_path / "catalog.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    assert len(read_catalog(csv_path)) == 2
    assert len(read_catalog(parquet_path)) == 2


def test_dry_run_generates_manifest_without_downloading(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    catalog_path = catalog_dir / "matches_catalog.parquet"
    _catalog_frame().to_parquet(catalog_path, index=False)
    config_path = _write_config(tmp_path, catalog_dir)

    manifest, outputs, summary = run_download_pipeline(config_path, dry_run=True)

    assert len(manifest) == 2
    assert outputs["csv"].exists()
    assert outputs["parquet"].exists()
    assert summary["total_missing_demo_link"] == 1
    assert set(manifest["download_status"]) == {"dry_run", "missing_demo_link"}
    assert not (tmp_path / "data/raw/demo_archives").exists()


def test_cli_runs_with_small_fake_catalog(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    catalog_path = catalog_dir / "matches_catalog.parquet"
    _catalog_frame().head(1).to_parquet(catalog_path, index=False)
    config_path = _write_config(tmp_path, catalog_dir)

    result = subprocess.run(
        [sys.executable, "-m", "src.ingestion.download_demos", "--config", str(config_path), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total de linhas do catalogo lidas: 1" in result.stdout
    assert (tmp_path / "data/bronze/demo_manifest/demo_manifest.csv").exists()


def test_local_only_does_not_create_http_clients(monkeypatch, tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    _catalog_frame().head(1).to_parquet(catalog_dir / "matches_catalog.parquet", index=False)
    config_path = _write_config(tmp_path, catalog_dir)
    archive_dir = tmp_path / "data/raw/demo_archives/Vitality/Mirage"
    archive_dir.mkdir(parents=True)
    (archive_dir / "hltv_42_mirage_map1.rar").write_bytes(b"fake rar")

    def fail_http_client(*args, **kwargs):
        raise AssertionError("HTTP client should not be created in --local-only mode")

    monkeypatch.setattr("src.ingestion.download_demos.DemoDownloader", fail_http_client)
    monkeypatch.setattr("src.ingestion.download_demos.HltvClient", fail_http_client)

    manifest, outputs, summary = run_download_pipeline(config_path, local_only=True, no_extract=True)

    assert outputs["csv"].exists()
    assert manifest.loc[0, "download_status"] == "local_existing"
    assert summary["total_local_existing"] == 1


def test_local_only_missing_archive_generates_manifest(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    _catalog_frame().head(1).to_parquet(catalog_dir / "matches_catalog.parquet", index=False)
    config_path = _write_config(tmp_path, catalog_dir)

    manifest, outputs, summary = run_download_pipeline(config_path, local_only=True)

    assert outputs["csv"].exists()
    assert manifest.loc[0, "download_status"] == "missing_local_archive"
    assert manifest.loc[0, "extract_status"] == "not_needed"
    assert manifest.loc[0, "status"] == "warning"
    assert summary["total_missing_local_archive"] == 1
    assert "hltv_42_mirage_map1" in manifest.loc[0, "error_message"]


def test_archive_path_copies_and_registers_local_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    _catalog_frame().head(1).to_parquet(catalog_dir / "matches_catalog.parquet", index=False)
    config_path = _write_config(tmp_path, catalog_dir)
    source_archive = tmp_path / "browser-download.rar"
    source_archive.write_bytes(b"fake rar")

    manifest, outputs, summary = run_download_pipeline(config_path, archive_path=source_archive, no_extract=True)
    target_archive = tmp_path / "data/raw/demo_archives/Vitality/Mirage/hltv_42_mirage_map1.rar"

    assert outputs["parquet"].exists()
    assert target_archive.exists()
    assert target_archive.read_bytes() == b"fake rar"
    assert manifest.loc[0, "download_status"] == "local_registered"
    assert manifest.loc[0, "archive_path"] == str(target_archive)
    assert summary["total_local_registered"] == 1


def test_local_zip_with_fake_dem_extracts(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    _catalog_frame().head(1).to_parquet(catalog_dir / "matches_catalog.parquet", index=False)
    config_path = _write_config(tmp_path, catalog_dir)
    archive_dir = tmp_path / "data/raw/demo_archives/Vitality/Mirage"
    archive_dir.mkdir(parents=True)
    archive_path = archive_dir / "hltv_42_mirage_map1.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/example.dem", b"fake demo")

    manifest, outputs, summary = run_download_pipeline(config_path, local_only=True)

    assert outputs["csv"].exists()
    assert manifest.loc[0, "download_status"] == "local_existing"
    assert manifest.loc[0, "extract_status"] == "extracted"
    assert Path(manifest.loc[0, "dem_path"]).exists()
    assert summary["total_extracted"] == 1
