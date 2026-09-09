from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.utils.io import read_table_pair, write_dataframe_outputs
from src.utils.logging import configure_logging


@dataclass(frozen=True)
class TimingContract:
    version: str
    default_tickrate: float
    default_source: str
    default_confidence: str
    expected_freeze_seconds: float
    tolerance_seconds: float
    overrides: tuple[dict[str, Any], ...]


def load_timing_contract(path: Path) -> TimingContract:
    if not path.exists():
        raise FileNotFoundError(f"Timing contract not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    validation = content.get("validation") or {}
    tickrate = float(content.get("default_tickrate") or 0)
    if tickrate <= 0:
        raise ValueError("default_tickrate must be greater than zero")
    return TimingContract(
        version=str(content.get("timing_contract_version") or "v1"),
        default_tickrate=tickrate,
        default_source=str(content.get("default_source") or "project_assumption"),
        default_confidence=str(content.get("default_confidence") or "assumed"),
        expected_freeze_seconds=float(validation.get("expected_freeze_seconds") or 20.0),
        tolerance_seconds=float(validation.get("tolerance_seconds") or 2.0),
        overrides=tuple(content.get("overrides") or []),
    )


def build_demo_timing(
    eligible: pd.DataFrame,
    rounds: pd.DataFrame,
    contract: TimingContract,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    explicit_columns = [name for name in ("tickrate", "tick_rate", "demo_tickrate") if name in eligible.columns]
    overrides = {str(row["parse_id"]): row for row in contract.overrides if row.get("parse_id")}
    timing_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for _, demo in eligible.drop_duplicates("parse_id").iterrows():
        parse_id = str(demo["parse_id"])
        tickrate = contract.default_tickrate
        source = contract.default_source
        confidence = contract.default_confidence
        method = "contract_default"
        explicit_value = next(
            (
                float(demo[column])
                for column in explicit_columns
                if pd.notna(demo.get(column)) and float(demo[column]) > 0
            ),
            None,
        )
        if explicit_value is not None:
            tickrate = explicit_value
            source = f"feature_eligible_demos.{explicit_columns[0]}"
            confidence = "observed"
            method = "parsed_metadata"
        if parse_id in overrides:
            override = overrides[parse_id]
            tickrate = float(override["tickrate"])
            source = str(override.get("source") or "documented_override")
            confidence = str(override.get("confidence") or "documented")
            method = "parse_override"

        timing_rows.append(
            {
                "parse_id": parse_id,
                "dem_file_id": demo.get("dem_file_id"),
                "series_id": demo.get("series_id"),
                "map_name": demo.get("inferred_map_name"),
                "tickrate": tickrate,
                "seconds_per_tick": 1.0 / tickrate,
                "timing_contract_version": contract.version,
                "tickrate_resolution_method": method,
                "tickrate_source": source,
                "tickrate_confidence": confidence,
            }
        )
        demo_rounds = rounds[rounds["source_parse_id"].astype(str) == parse_id] if not rounds.empty else rounds
        deltas = pd.to_numeric(demo_rounds.get("freeze_end"), errors="coerce") - pd.to_numeric(
            demo_rounds.get("start"), errors="coerce"
        )
        plausible = deltas[(deltas > 0) & (deltas <= tickrate * 30)]
        median_seconds = float(np.median(plausible) / tickrate) if len(plausible) else np.nan
        within_tolerance = bool(
            np.isfinite(median_seconds)
            and abs(median_seconds - contract.expected_freeze_seconds) <= contract.tolerance_seconds
        )
        audit_rows.append(
            {
                "parse_id": parse_id,
                "tickrate": tickrate,
                "freeze_samples": int(len(plausible)),
                "median_freeze_seconds": median_seconds,
                "expected_freeze_seconds": contract.expected_freeze_seconds,
                "tolerance_seconds": contract.tolerance_seconds,
                "timing_evidence_status": "consistent" if within_tolerance else "insufficient_or_inconsistent",
            }
        )
    return pd.DataFrame(timing_rows), pd.DataFrame(audit_rows)


def run_demo_timing_pipeline(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    silver_dir = project.parsed_silver_dir if project.parsed_silver_dir.is_absolute() else project_root / project.parsed_silver_dir
    contract_path = (
        project.timing_config_path
        if project.timing_config_path.is_absolute()
        else project_root / project.timing_config_path
    )
    eligible = read_table_pair(silver_dir / "feature_eligible_demos")
    rounds = read_table_pair(silver_dir / "rounds")
    timing, audit = build_demo_timing(eligible, rounds, load_timing_contract(contract_path))
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(
            write_dataframe_outputs(
                {"demo_timing": timing},
                silver_dir,
                force=force,
                formats=tuple(project.output_formats),
            )
        )
        outputs.update(
            write_dataframe_outputs(
                {"demo_timing_audit": audit},
                project_root / "data/gold/features/demo_timing",
                force=force,
                formats=tuple(project.output_formats),
            )
        )
    return timing, audit, outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve the tickrate contract for each feature-eligible demo.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configure_logging()
    timing, audit, outputs = run_demo_timing_pipeline(args.config, force=args.force, dry_run=args.dry_run)
    print(
        {
            "demos": len(timing),
            "tickrates": sorted(timing["tickrate"].dropna().unique().tolist()),
            "consistent": int((audit["timing_evidence_status"] == "consistent").sum()),
            "outputs": {key: str(value) for key, value in outputs.items()},
        }
    )


if __name__ == "__main__":
    main()
