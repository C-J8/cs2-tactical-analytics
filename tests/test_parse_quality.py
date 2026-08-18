from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.parsing.parse_quality import build_parse_quality, run_quality_pipeline


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


def _parse_row(
    demo_record_id: str,
    *,
    map_name: str = "Mirage",
    parse_status: str = "parsed",
    rounds: int | None = 13,
    ticks: int | None = 100,
) -> dict[str, object]:
    return {
        "parse_id": f"{demo_record_id}_awpy",
        "series_id": "series1",
        "hltv_match_id": None,
        "match_date": None,
        "event_name": None,
        "target_team": "Vitality",
        "opponent": "unknown",
        "map_name": map_name,
        "map_number": 1,
        "dem_path": f"{demo_record_id}.dem",
        "dem_file_name": f"{demo_record_id}.dem",
        "dem_file_size_bytes": 1,
        "dem_sha256": "fake",
        "parser_backend": "awpy",
        "parser_version": "test",
        "parse_status": parse_status,
        "parse_error_message": None,
        "parsed_at": "now",
        "output_bronze_dir": "out",
        "rows_rounds": rounds,
        "rows_kills": 1,
        "rows_damages": 1,
        "rows_shots": 1,
        "rows_bomb": 1,
        "rows_smokes": 1,
        "rows_infernos": 1,
        "rows_grenades": 1,
        "rows_footsteps": 1,
        "rows_ticks": ticks,
        "rows_events_total": 1,
        "demo_record_id": demo_record_id,
    }


def _dem_row(
    dem_file_id: str,
    *,
    inferred_map_name: str = "Mirage",
    parse_eligible: bool = True,
    is_split_segment: bool = False,
    is_merged_demo: bool = False,
) -> dict[str, object]:
    return {
        "dem_file_id": dem_file_id,
        "local_archive_id": "archive1",
        "archive_file_name": "archive.rar",
        "inferred_map_name": inferred_map_name,
        "parse_eligible": parse_eligible,
        "is_split_segment": is_split_segment,
        "is_merged_demo": is_merged_demo,
    }


def _quality_for(parse_row: dict[str, object], dem_row: dict[str, object] | None = None, *, min_rounds: int = 12) -> pd.DataFrame:
    return build_parse_quality(
        pd.DataFrame([parse_row]),
        pd.DataFrame([dem_row or _dem_row(str(parse_row["demo_record_id"]))]),
        pd.DataFrame(),
        target_maps={"Mirage"},
        min_rounds=min_rounds,
    )


def test_valid_full_map_is_feature_eligible() -> None:
    quality = _quality_for(_parse_row("valid", rounds=13, ticks=100))

    assert quality.loc[0, "quality_status"] == "valid_full_map"
    assert bool(quality.loc[0, "feature_eligible"]) is True


def test_short_demo_is_not_feature_eligible() -> None:
    quality = _quality_for(_parse_row("short", rounds=5, ticks=100))

    assert quality.loc[0, "quality_status"] == "suspicious_short_demo"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_missing_ticks() -> None:
    quality = _quality_for(_parse_row("no_ticks", rounds=13, ticks=0))

    assert quality.loc[0, "quality_status"] == "missing_ticks"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_missing_rounds() -> None:
    quality = _quality_for(_parse_row("no_rounds", rounds=0, ticks=100))

    assert quality.loc[0, "quality_status"] == "missing_rounds"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_map_not_target() -> None:
    quality = _quality_for(_parse_row("nuke", map_name="Nuke", rounds=13, ticks=100), _dem_row("nuke", inferred_map_name="Nuke"))

    assert quality.loc[0, "quality_status"] == "map_not_target"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_split_segment_not_used() -> None:
    quality = _quality_for(
        _parse_row("split", parse_status="split_segment_merged", rounds=0, ticks=0),
        _dem_row("split", parse_eligible=False, is_split_segment=True),
    )

    assert quality.loc[0, "quality_status"] == "split_segment_not_used"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_parse_failed() -> None:
    quality = _quality_for(_parse_row("failed", parse_status="failed", rounds=0, ticks=0))

    assert quality.loc[0, "quality_status"] == "parse_failed"
    assert bool(quality.loc[0, "feature_eligible"]) is False


def test_pipeline_writes_quality_and_feature_eligible_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    parse_manifest_path = tmp_path / "data/bronze/parse_manifest/parse_manifest.parquet"
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    parse_manifest_path.parent.mkdir(parents=True)
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame([_parse_row("valid"), _parse_row("short", rounds=5)]).to_parquet(parse_manifest_path, index=False)
    pd.DataFrame([_dem_row("valid"), _dem_row("short")]).to_parquet(dem_files_path, index=False)

    quality, feature_eligible, outputs, summary = run_quality_pipeline(config_path, force=True)

    assert len(quality) == 2
    assert len(feature_eligible) == 1
    assert summary["total_feature_eligible"] == 1
    assert outputs["parse_quality_csv"].exists()
    assert outputs["feature_eligible_demos_parquet"].exists()
    assert (tmp_path / "data/silver/parsed_demos/feature_eligible_demos.csv").exists()


def test_dry_run_does_not_overwrite_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    parse_manifest_path = tmp_path / "data/bronze/parse_manifest/parse_manifest.parquet"
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    output_path = tmp_path / "data/bronze/parse_quality/parse_quality.csv"
    parse_manifest_path.parent.mkdir(parents=True)
    dem_files_path.parent.mkdir(parents=True)
    output_path.parent.mkdir(parents=True)
    output_path.write_text("sentinel", encoding="utf-8")
    pd.DataFrame([_parse_row("valid")]).to_parquet(parse_manifest_path, index=False)
    pd.DataFrame([_dem_row("valid")]).to_parquet(dem_files_path, index=False)

    _, _, outputs, _ = run_quality_pipeline(config_path, dry_run=True)

    assert outputs == {}
    assert output_path.read_text(encoding="utf-8") == "sentinel"


def test_parse_quality_target_map_inferno_recognizes_de_inferno(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    parse_manifest_path = tmp_path / "data/bronze/parse_manifest/parse_manifest.parquet"
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    parse_manifest_path.parent.mkdir(parents=True)
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame([_parse_row("inferno", map_name="de_inferno", rounds=13, ticks=100)]).to_parquet(parse_manifest_path, index=False)
    pd.DataFrame([_dem_row("inferno", inferred_map_name="de_inferno")]).to_parquet(dem_files_path, index=False)

    quality, feature_eligible, _, summary = run_quality_pipeline(config_path, dry_run=True, target_maps=["Inferno"], target_team="Vitality")

    assert len(quality) == 1
    assert quality.loc[0, "quality_status"] == "valid_full_map"
    assert len(feature_eligible) == 1
    assert summary["total_map_not_target"] == 0


def test_scoped_parse_quality_preserves_mirage_feature_eligibility(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    parse_manifest_path = tmp_path / "data/bronze/parse_manifest/parse_manifest.parquet"
    dem_files_path = tmp_path / "data/bronze/dem_files_manifest/dem_files_manifest.parquet"
    parse_manifest_path.parent.mkdir(parents=True)
    dem_files_path.parent.mkdir(parents=True)
    pd.DataFrame([_parse_row("inferno", map_name="de_inferno", rounds=13, ticks=100)]).to_parquet(parse_manifest_path, index=False)
    pd.DataFrame([_dem_row("inferno", inferred_map_name="de_inferno")]).to_parquet(dem_files_path, index=False)
    existing_silver = tmp_path / "data/silver/parsed_demos"
    existing_quality = tmp_path / "data/bronze/parse_quality"
    existing_silver.mkdir(parents=True)
    existing_quality.mkdir(parents=True)
    mirage_quality = build_parse_quality(
        pd.DataFrame([_parse_row("mirage", map_name="Mirage")]),
        pd.DataFrame([_dem_row("mirage", inferred_map_name="Mirage")]),
        pd.DataFrame(),
        target_maps={"Mirage"},
        min_rounds=12,
    )
    mirage_quality.to_parquet(existing_quality / "parse_quality.parquet", index=False)
    mirage_quality.to_parquet(existing_silver / "feature_eligible_demos.parquet", index=False)

    final_quality, final_feature_eligible, _, _ = run_quality_pipeline(config_path, force=True, target_maps=["Inferno"], target_team="Vitality")

    assert {"mirage_awpy", "inferno_awpy"} <= set(final_quality["parse_id"])
    assert {"mirage_awpy", "inferno_awpy"} <= set(final_feature_eligible["parse_id"])
    assert final_quality["parse_id"].is_unique
