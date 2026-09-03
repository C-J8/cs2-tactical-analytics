from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.utils.io import read_optional_table, read_table_pair, write_dataframe_outputs
from src.utils.notebooks import code, md, notebook_json, write_notebook
from src.utils.reports import markdown_table, safe_divide


def test_write_dataframe_outputs_writes_csv_and_parquet(tmp_path: Path) -> None:
    frames = {"sample": pd.DataFrame([{"value": 1}])}

    outputs = write_dataframe_outputs(frames, tmp_path, force=True)

    assert outputs["sample_csv"].exists()
    assert outputs["sample_parquet"].exists()
    assert pd.read_csv(outputs["sample_csv"]).iloc[0]["value"] == 1
    assert pd.read_parquet(outputs["sample_parquet"]).iloc[0]["value"] == 1


def test_write_dataframe_outputs_writes_empty_frame_and_overwrites_with_force(tmp_path: Path) -> None:
    existing = tmp_path / "sample.csv"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("value\nold\n", encoding="utf-8")

    outputs = write_dataframe_outputs({"sample": pd.DataFrame(columns=["value"])}, tmp_path, force=True, formats=("csv", "parquet"))

    assert outputs["sample_csv"].read_text(encoding="utf-8").strip() == "value"
    assert pd.read_parquet(outputs["sample_parquet"]).empty


def test_write_dataframe_outputs_respects_existing_without_force(tmp_path: Path) -> None:
    existing = tmp_path / "sample.csv"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("value\nold\n", encoding="utf-8")

    write_dataframe_outputs({"sample": pd.DataFrame([{"value": "new"}])}, tmp_path, force=False, formats=("csv",))

    assert existing.read_text(encoding="utf-8") == "value\nold\n"


def test_read_table_pair_prefers_parquet_and_optional_missing_returns_empty(tmp_path: Path) -> None:
    base = tmp_path / "table"
    pd.DataFrame([{"source": "csv"}]).to_csv(base.with_suffix(".csv"), index=False)
    pd.DataFrame([{"source": "parquet"}]).to_parquet(base.with_suffix(".parquet"), index=False)

    assert read_table_pair(base).iloc[0]["source"] == "parquet"
    assert read_optional_table(tmp_path / "missing.parquet").empty


def test_read_table_pair_string_preserving_csv_policy(tmp_path: Path) -> None:
    base = tmp_path / "ids"
    base.with_suffix(".csv").write_text("id,empty,code\n00123,,NA\n", encoding="utf-8")

    frame = read_table_pair(base, csv_policy="string_preserving")

    assert frame.iloc[0]["id"] == "00123"
    assert frame.iloc[0]["empty"] == ""
    assert frame.iloc[0]["code"] == "NA"


def test_read_table_pair_default_csv_policy_keeps_numeric_inference(tmp_path: Path) -> None:
    base = tmp_path / "numbers"
    base.with_suffix(".csv").write_text("value\n42\n", encoding="utf-8")

    frame = read_table_pair(base)

    assert frame.iloc[0]["value"] == 42


def test_read_table_pair_unsupported_csv_policy_fails(tmp_path: Path) -> None:
    base = tmp_path / "table"
    base.with_suffix(".csv").write_text("value\n1\n", encoding="utf-8")

    try:
        read_table_pair(base, csv_policy="mystery")
    except ValueError as exc:
        assert "Unsupported CSV policy" in str(exc)
    else:
        raise AssertionError("Unsupported CSV policy should fail")


def test_notebook_helpers_write_output_free_notebook(tmp_path: Path) -> None:
    path = tmp_path / "notebook.ipynb"

    write_notebook(path, [md("# Title"), code("1 + 1")], force=True)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["nbformat"] == 4
    assert payload["cells"][0]["cell_type"] == "markdown"
    assert payload["cells"][1]["outputs"] == []
    assert json.loads(notebook_json([code("x = 1")]))["cells"][0]["execution_count"] is None
    write_notebook(path, [md("# Changed")], force=False)
    assert json.loads(path.read_text(encoding="utf-8"))["cells"][0]["source"] == ["# Title"]


def test_report_helpers_handle_empty_tables_and_zero_division() -> None:
    assert safe_divide(1, 0) is None
    assert safe_divide("6", "3") == 2.0
    assert markdown_table(pd.DataFrame(), ["a"]) == "_No rows._"
    assert markdown_table(pd.DataFrame([{"other": 1}]), ["missing"]) == "_No requested columns available._"
    assert "nan" not in markdown_table(pd.DataFrame([{"value": None}]), ["value"]).lower()
    assert "value" in markdown_table(pd.DataFrame([{"value": 1, "extra": 2}]), ["value"])
    assert markdown_table(pd.DataFrame([{"value": 1}, {"value": 2}]), ["value"], top_n=1).count("\n") < 4
