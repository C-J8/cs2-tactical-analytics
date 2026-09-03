from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis import t_side_eda, t_side_findings, tactical_finding_hardening
from src.maps import build_map_registry
from src.validation import multi_map_gold_gate


def test_representative_write_wrappers_preserve_output_contracts(tmp_path: Path) -> None:
    modules = [
        (t_side_eda.OUTPUT_NAMES, t_side_eda.write_outputs),
        (t_side_findings.FINDING_OUTPUT_NAMES, t_side_findings.write_outputs),
        (build_map_registry.OUTPUT_NAMES, build_map_registry.write_outputs),
        (multi_map_gold_gate.OUTPUT_NAMES, multi_map_gold_gate.write_outputs),
        (tactical_finding_hardening.OUTPUT_NAMES, tactical_finding_hardening.write_outputs),
    ]

    for index, (names, writer) in enumerate(modules):
        output_dir = tmp_path / f"module_{index}"
        frames = {name: pd.DataFrame([{"stable_key": name, "status": "ok"}]) for name in names}

        outputs = writer(frames, output_dir, force=True)

        assert set(outputs) == {f"{name}_{suffix}" for name in names for suffix in ["csv", "parquet"]}
        for name in names:
            csv_frame = pd.read_csv(output_dir / f"{name}.csv")
            parquet_frame = pd.read_parquet(output_dir / f"{name}.parquet")
            assert list(csv_frame.columns) == ["stable_key", "status"]
            assert list(parquet_frame.columns) == ["stable_key", "status"]
            assert len(csv_frame) == 1
            assert parquet_frame.iloc[0]["stable_key"] == name


def test_representative_write_wrappers_respect_force_false(tmp_path: Path) -> None:
    output_dir = tmp_path / "eda"
    frames = {name: pd.DataFrame([{"stable_key": "new", "status": "ok"}]) for name in t_side_eda.OUTPUT_NAMES}

    t_side_eda.write_outputs(frames, output_dir, force=True)
    first_name = t_side_eda.OUTPUT_NAMES[0]
    (output_dir / f"{first_name}.csv").write_text("stable_key,status\nold,ok\n", encoding="utf-8")
    t_side_eda.write_outputs(frames, output_dir, force=False)

    assert pd.read_csv(output_dir / f"{first_name}.csv").iloc[0]["stable_key"] == "old"
