from pathlib import Path

import pandas as pd
import polars as pl
import pyarrow.parquet as pq
import pytest

import src.storage.silver_tables as silver_tables
from src.storage.silver_tables import (
    partition_file_name,
    read_silver_table,
    silver_scan_source,
    silver_partition_files,
    silver_table_exists,
    write_partitioned_silver_table,
)


def test_partitioned_ticks_round_trip_and_scope_replacement(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    registry = Path("configs/maps/map_registry.yaml")
    initial = pd.DataFrame(
        {
            "source_parse_id": ["parse-a", "parse-a", "parse-b"],
            "target_team": ["Vitality"] * 3,
            "map_name": ["Mirage"] * 3,
            "round_num": [1, 1, 2],
            "tick": [10, 20, 30],
            "steamid": [1, 1, 2],
        }
    )

    outputs = write_partitioned_silver_table(
        silver,
        "ticks",
        initial,
        parse_ids={"parse-a", "parse-b"},
        registry_path=registry,
    )

    assert len(outputs) == 2
    assert outputs[0].parent.name == "map_id=mirage"
    assert pq.ParquetFile(outputs[0]).metadata.row_group(0).column(0).compression == "ZSTD"
    assert silver_table_exists(silver, "ticks")
    assert len(read_silver_table(silver, "ticks")) == 3
    assert pl.scan_parquet(silver_scan_source(silver, "ticks")).select(pl.len()).collect().item() == 3

    replacement = initial[initial["source_parse_id"] == "parse-a"].iloc[:1].copy()
    write_partitioned_silver_table(
        silver,
        "ticks",
        replacement,
        parse_ids={"parse-a"},
        registry_path=registry,
    )

    final = read_silver_table(silver, "ticks")
    assert len(final) == 2
    assert (silver / "table=ticks" / "target_team=vitality" / "map_id=mirage" / partition_file_name("parse-b")).exists()


def test_monolith_remains_readable_during_pre_migration_compatibility(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    silver.mkdir()
    pd.DataFrame({"source_parse_id": ["legacy"], "tick": [1]}).to_parquet(silver / "ticks.parquet", index=False)

    assert silver_table_exists(silver, "ticks")
    assert read_silver_table(silver, "ticks")["source_parse_id"].tolist() == ["legacy"]


def test_failed_partition_promotion_restores_previous_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    silver = tmp_path / "silver"
    registry = Path("configs/maps/map_registry.yaml")
    initial = pd.DataFrame(
        {
            "source_parse_id": ["parse-a"],
            "target_team": ["Vitality"],
            "map_name": ["Mirage"],
            "tick": [10],
        }
    )
    write_partitioned_silver_table(silver, "ticks", initial, parse_ids={"parse-a"}, registry_path=registry)
    original_replace = silver_tables.os.replace

    def fail_new_partition(source: str | Path, destination: str | Path) -> None:
        if Path(source).parent.name == "new":
            raise OSError("simulated promotion failure")
        original_replace(source, destination)

    monkeypatch.setattr(silver_tables.os, "replace", fail_new_partition)
    replacement = initial.assign(tick=99)
    with pytest.raises(OSError, match="simulated promotion failure"):
        write_partitioned_silver_table(silver, "ticks", replacement, parse_ids={"parse-a"}, registry_path=registry)

    assert read_silver_table(silver, "ticks")["tick"].tolist() == [10]


def test_temporary_files_are_not_active_partitions(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    root = silver / "table=ticks" / "target_team=vitality" / "map_id=mirage"
    root.mkdir(parents=True)
    pd.DataFrame({"source_parse_id": ["partial"]}).to_parquet(root / "parse-partial.tmp.parquet", index=False)

    assert not silver_partition_files(silver, "ticks")
