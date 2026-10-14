from pathlib import Path

import pandas as pd
import pytest

import src.storage.migrate_silver_ticks as migration
from src.storage.migrate_silver_ticks import run_ticks_migration
from src.storage.silver_tables import read_silver_table, silver_partition_files


def write_config(root: Path) -> Path:
    configs = root / "configs"
    configs.mkdir(parents=True)
    config = configs / "project.yaml"
    config.write_text(
        f"""
project_name: test
mode: manual
date_start: 2025-01-01
date_end: 2026-12-31
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(root / 'data/silver/parsed_demos').as_posix()}
""",
        encoding="utf-8",
    )
    (configs / "storage.yaml").write_text(
        """
storage_version: v1
roots:
  migration_rollback: data/raw/quarantine/storage_migrations
audit:
  silver_ticks_migration: data/gold/validation/silver_ticks_migration
""",
        encoding="utf-8",
    )
    return config


def ticks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_parse_id": ["parse-a", "parse-a", "parse-b"],
            "target_team": ["Vitality"] * 3,
            "map_name": ["Mirage"] * 3,
            "round_num": [1, 1, 2],
            "tick": [10, 20, 30],
            "steamid": [1, 1, 2],
        }
    )


def test_migration_proves_parity_and_moves_monolith_to_rollback(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    ticks().to_parquet(silver / "ticks.parquet", index=False)

    frames, outputs, summary = run_ticks_migration(config, run_id="test_run", force=False)

    audit = frames["silver_ticks_migration_audit"].iloc[0]
    assert summary["status"] == "passed"
    assert summary["source_rows"] == summary["partition_rows"] == 3
    assert audit["schema_match"]
    assert audit["per_parse_count_match"]
    assert audit["content_fingerprint_match"]
    assert audit["rollback_hash_match"]
    assert audit["source_sha256"] == audit["rollback_sha256"]
    assert len(silver_partition_files(silver, "ticks")) == 2
    assert len(read_silver_table(silver, "ticks")) == 3
    assert not (silver / "ticks.parquet").exists()
    assert (tmp_path / "data/raw/quarantine/storage_migrations/test_run/ticks.parquet").exists()
    assert outputs["silver_ticks_migration_audit_parquet"].exists()


def test_dry_run_leaves_monolith_untouched(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    ticks().to_parquet(silver / "ticks.parquet", index=False)

    frames, outputs, summary = run_ticks_migration(config, run_id="dry_run", dry_run=True)

    assert summary["status"] == "dry_run"
    assert (silver / "ticks.parquet").exists()
    assert not silver_partition_files(silver, "ticks")
    assert outputs == {}
    assert len(frames["silver_ticks_partition_plan"]) == 2


def test_default_run_id_is_valid_and_plan_uses_canonical_map_id(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    frame = ticks().assign(map_name="de_inferno")
    frame.to_parquet(silver / "ticks.parquet", index=False)

    frames, _, summary = run_ticks_migration(config, dry_run=True)

    assert str(summary["run_id"]).startswith("ticks_")
    assert frames["silver_ticks_partition_plan"]["planned_relative_path"].str.contains("map_id=inferno").all()


def test_existing_partitions_are_revalidated_without_overwriting_evidence(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    ticks().to_parquet(silver / "ticks.parquet", index=False)
    _, original_outputs, _ = run_ticks_migration(config, run_id="first_run")
    audit_path = original_outputs["silver_ticks_migration_audit_parquet"]
    original_bytes = audit_path.read_bytes()

    frames, outputs, summary = run_ticks_migration(config, run_id="ignored_second_run", force=True)

    assert summary["status"] == "passed"
    assert frames["silver_ticks_migration_audit"].iloc[0]["run_id"] == "first_run"
    assert outputs == {}
    assert audit_path.read_bytes() == original_bytes


def test_migration_rolls_back_when_audit_persistence_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = write_config(tmp_path)
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    source = silver / "ticks.parquet"
    ticks().to_parquet(source, index=False)

    def fail_audit(*args: object, **kwargs: object) -> dict[str, Path]:
        raise OSError("simulated audit failure")

    monkeypatch.setattr(migration, "write_dataframe_outputs", fail_audit)
    with pytest.raises(OSError, match="simulated audit failure"):
        run_ticks_migration(config, run_id="rollback_test")

    assert source.exists()
    assert not silver_partition_files(silver, "ticks")
    assert not (tmp_path / "data/raw/quarantine/storage_migrations/rollback_test").exists()
