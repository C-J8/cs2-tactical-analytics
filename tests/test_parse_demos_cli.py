from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.parsing.awpy_parser import ParsedDemo
from src.parsing.parse_demos import run_parse_pipeline
from src.parsing.parsed_tables import TRACE_COLUMNS, write_silver_tables


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
demo_manifest_path: {manifest_path.as_posix()}
dem_files_manifest_path: {(tmp_path / 'data/bronze/dem_files_manifest/dem_files_manifest.parquet').as_posix()}
parsed_bronze_dir: {(tmp_path / 'data/bronze/parsed_demos').as_posix()}
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
parse_manifest_dir: {(tmp_path / 'data/bronze/parse_manifest').as_posix()}
parser_backend: awpy
parse_player_props:
  - X
  - Y
parse_tables:
  - rounds
  - grenades
  - ticks
parse_events: true
download_timeout_seconds: 10
download_rate_limit_seconds: 0
extract_archives: true
force_download: false
max_demos_per_run: null
force_parse: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _manifest_row(dem_path: Path | str, *, status: str = "ok", demo_record_id: str = "demo1") -> dict[str, object]:
    return {
        "demo_record_id": demo_record_id,
        "series_id": "hltv_42",
        "hltv_match_id": "42",
        "match_date": "2026-01-01",
        "event_name": "Example",
        "target_team": "Vitality",
        "opponent": "NAVI",
        "map_name": "Mirage",
        "map_number": 1,
        "dem_path": str(dem_path),
        "dem_file_name": Path(str(dem_path)).name,
        "dem_file_size_bytes": 4,
        "dem_sha256": "fake",
        "status": status,
    }


@dataclass
class FakeParser:
    player_props: list[str]
    parse_tables: list[str]
    parse_events: bool

    def parse(self, dem_path: Path) -> ParsedDemo:
        if "fail" in dem_path.name:
            raise RuntimeError("parser exploded")
        return ParsedDemo(
            tables={
                "rounds": pd.DataFrame({"round_num": [1]}),
                "grenades": pd.DataFrame({"grenade_type": ["smoke"]}),
                "ticks": pd.DataFrame({"tick": [1], "X": [10]}),
            },
            events={"player_death": pd.DataFrame({"tick": [2]})},
            parser_version="test",
        )


def test_parse_manifest_missing_dem(tmp_path: Path) -> None:
    manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([_manifest_row(tmp_path / "missing.dem")]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    parse_manifest, outputs, summary = run_parse_pipeline(config_path, parser_class=FakeParser)

    assert outputs["csv"].exists()
    assert parse_manifest.loc[0, "parse_status"] == "missing_dem"
    assert summary["total_missing_dem"] == 1


def test_parse_demos_dry_run_does_not_call_parser(tmp_path: Path) -> None:
    dem_path = tmp_path / "fake.dem"
    dem_path.write_bytes(b"fake")
    manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    class ExplodingParser(FakeParser):
        def parse(self, dem_path: Path) -> ParsedDemo:
            raise AssertionError("dry-run should not parse")

    parse_manifest, _, summary = run_parse_pipeline(config_path, dry_run=True, parser_class=ExplodingParser)

    assert parse_manifest.loc[0, "parse_status"] == "dry_run"
    assert summary["total_dry_run"] == 1


def test_parse_demos_cli_no_eligible_demos(tmp_path: Path) -> None:
    manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([_manifest_row("", status="warning")]).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    result = subprocess.run(
        [sys.executable, "-m", "src.parsing.parse_demos", "--config", str(config_path), "--manifest", str(manifest_path), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total elegiveis para parsing: 0" in result.stdout
    assert (tmp_path / "data/bronze/parse_manifest/parse_manifest.csv").exists()


def test_write_parsed_tables_and_trace_columns(tmp_path: Path) -> None:
    row = _manifest_row(tmp_path / "fake.dem")
    tables = {"ticks": pd.DataFrame({"tick": [1], "X": [10]})}

    traced = write_silver_tables(tables, row, "parse1", tmp_path)

    assert (tmp_path / "ticks.parquet").exists()
    assert all(column in traced["ticks"].columns for column in TRACE_COLUMNS)


def test_parse_continues_after_one_failure(tmp_path: Path) -> None:
    fail_dem = tmp_path / "fail.dem"
    ok_dem = tmp_path / "ok.dem"
    fail_dem.write_bytes(b"fail")
    ok_dem.write_bytes(b"ok")
    manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame(
        [
            _manifest_row(fail_dem, demo_record_id="demo_fail"),
            _manifest_row(ok_dem, demo_record_id="demo_ok"),
        ]
    ).to_parquet(manifest_path, index=False)
    config_path = _write_config(tmp_path, manifest_path)

    parse_manifest, _, summary = run_parse_pipeline(config_path, parser_class=FakeParser)

    assert parse_manifest["parse_status"].tolist() == ["failed", "parsed"]
    assert summary["total_failed"] == 1
    assert summary["total_parsed"] == 1
    assert (tmp_path / "data/silver/parsed_demos/ticks.parquet").exists()


def test_parse_demos_uses_dem_files_manifest_and_filters_maps(tmp_path: Path) -> None:
    dem_mirage = tmp_path / "mirage.dem"
    dem_nuke = tmp_path / "nuke.dem"
    dem_mirage.write_bytes(b"mirage")
    dem_nuke.write_bytes(b"nuke")
    demo_manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([]).to_parquet(demo_manifest_path, index=False)
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "dem_file_id": "mirage1",
                "local_archive_id": "archive1",
                "dem_path": str(dem_mirage),
                "dem_file_name": dem_mirage.name,
                "target_team": "Vitality",
                "assumed_map": "Mirage",
                "inferred_map_name": "Mirage",
                "inferred_map_number": 1,
            },
            {
                "dem_file_id": "nuke1",
                "local_archive_id": "archive2",
                "dem_path": str(dem_nuke),
                "dem_file_name": dem_nuke.name,
                "target_team": "Vitality",
                "assumed_map": "Mirage",
                "inferred_map_name": "Nuke",
                "inferred_map_number": 2,
            },
        ]
    ).to_parquet(dem_files_path, index=False)
    config_path = _write_config(tmp_path, demo_manifest_path)

    parse_manifest, _, summary = run_parse_pipeline(config_path, dry_run=True)

    assert summary["total_eligible"] == 1
    dry_run_rows = parse_manifest[parse_manifest["parse_status"] == "dry_run"]
    assert dry_run_rows.iloc[0]["dem_file_name"] == "mirage.dem"
    assert "map_not_target" in set(parse_manifest["parse_status"])


def test_parse_demos_unknown_map_requires_flag_or_assume_map(tmp_path: Path) -> None:
    dem_path = tmp_path / "unknown.dem"
    dem_path.write_bytes(b"fake")
    demo_manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([]).to_parquet(demo_manifest_path, index=False)
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "dem_file_id": "unknown1",
                "local_archive_id": "archive1",
                "dem_path": str(dem_path),
                "dem_file_name": dem_path.name,
                "target_team": "Vitality",
                "assumed_map": "Mirage",
                "inferred_map_name": "unknown",
                "inferred_map_number": None,
            }
        ]
    ).to_parquet(dem_files_path, index=False)
    config_path = _write_config(tmp_path, demo_manifest_path)

    skipped, _, skipped_summary = run_parse_pipeline(config_path, dry_run=True)
    allowed, _, allowed_summary = run_parse_pipeline(config_path, dry_run=True, allow_unknown_map=True)
    assumed, _, assumed_summary = run_parse_pipeline(config_path, dry_run=True, assume_map="Mirage")

    assert skipped.loc[0, "parse_status"] == "map_unknown"
    assert skipped_summary["total_eligible"] == 0
    assert allowed_summary["total_eligible"] == 1
    assert allowed.loc[0, "map_name"] == "unknown"
    assert assumed_summary["total_eligible"] == 1
    assert assumed.loc[0, "map_name"] == "Mirage"


def test_parse_demos_records_map_not_target_skip(tmp_path: Path) -> None:
    dem_path = tmp_path / "nuke.dem"
    dem_path.write_bytes(b"fake")
    demo_manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([]).to_parquet(demo_manifest_path, index=False)
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "dem_file_id": "nuke1",
                "local_archive_id": "archive1",
                "dem_path": str(dem_path),
                "dem_file_name": dem_path.name,
                "target_team": "Vitality",
                "assumed_map": "Mirage",
                "inferred_map_name": "Nuke",
                "inferred_map_number": 1,
            }
        ]
    ).to_parquet(dem_files_path, index=False)
    config_path = _write_config(tmp_path, demo_manifest_path)

    parse_manifest, _, summary = run_parse_pipeline(config_path, dry_run=True)

    assert parse_manifest.loc[0, "parse_status"] == "map_not_target"
    assert summary["total_eligible"] == 0


def test_parse_demos_skips_not_parse_eligible_rows(tmp_path: Path) -> None:
    dem_path = tmp_path / "split-p1.dem"
    dem_path.write_bytes(b"fake")
    demo_manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([]).to_parquet(demo_manifest_path, index=False)
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "dem_file_id": "split1",
                "local_archive_id": "archive1",
                "dem_path": str(dem_path),
                "dem_file_name": dem_path.name,
                "target_team": "Vitality",
                "assumed_map": "Mirage",
                "inferred_map_name": "Mirage",
                "inferred_map_number": 1,
                "parse_eligible": False,
                "exclusion_reason": "split_segment_merged",
            }
        ]
    ).to_parquet(dem_files_path, index=False)
    config_path = _write_config(tmp_path, demo_manifest_path)

    parse_manifest, _, summary = run_parse_pipeline(config_path, dry_run=True)

    assert parse_manifest.loc[0, "parse_status"] == "split_segment_merged"
    assert summary["total_eligible"] == 0


def test_force_parse_clears_silver_and_writes_parse_audit(tmp_path: Path) -> None:
    dem_path = tmp_path / "fake.dem"
    dem_path.write_bytes(b"fake")
    manifest_path = tmp_path / "demo_manifest.parquet"
    pd.DataFrame([_manifest_row(dem_path)]).to_parquet(manifest_path, index=False)
    silver_dir = tmp_path / "data/silver/parsed_demos"
    silver_dir.mkdir(parents=True)
    pd.DataFrame({"tick": [0], "source_parse_id": ["stale"]}).to_parquet(silver_dir / "ticks.parquet", index=False)
    config_path = _write_config(tmp_path, manifest_path)

    parse_manifest, outputs, summary = run_parse_pipeline(config_path, force=True, parser_class=FakeParser)
    ticks = pd.read_parquet(silver_dir / "ticks.parquet")
    audit = pd.read_parquet(tmp_path / "data/bronze/parse_audit/parse_audit.parquet")

    assert parse_manifest.loc[0, "parse_status"] == "parsed"
    assert summary["total_parsed"] == 1
    assert "stale" not in set(ticks["source_parse_id"])
    assert outputs["parse_audit_csv"].exists()
    assert {"ticks", "rounds", "grenades"}.issubset(set(audit["table_name"]))
    assert bool(audit[audit["table_name"] == "ticks"].iloc[0]["has_tick"]) is True
