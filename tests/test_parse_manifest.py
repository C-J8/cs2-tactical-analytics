from __future__ import annotations

import pandas as pd

from src.parsing.parse_manifest import PARSE_MANIFEST_COLUMNS, empty_parse_manifest, write_parse_manifest


def test_write_parse_manifest(tmp_path) -> None:
    df = pd.DataFrame([{"parse_id": "p1", "parse_status": "dry_run"}])

    outputs = write_parse_manifest(df, tmp_path, ["csv", "parquet"])

    assert outputs["csv"].exists()
    assert outputs["parquet"].exists()
    written = pd.read_parquet(outputs["parquet"])
    assert list(written.columns) == PARSE_MANIFEST_COLUMNS
    assert written.loc[0, "parse_status"] == "dry_run"


def test_empty_parse_manifest_has_schema() -> None:
    assert list(empty_parse_manifest().columns) == PARSE_MANIFEST_COLUMNS
