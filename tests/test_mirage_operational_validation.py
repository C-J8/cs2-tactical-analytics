import hashlib
import zipfile
from pathlib import Path

import pandas as pd
import yaml

from src.validation.mirage_operational_validation import (
    DatasetSpec,
    compare_fingerprints,
    fingerprint_dataset,
    prepare_isolated_project,
    run_retention_recovery,
)


def test_logical_fingerprint_ignores_execution_timestamps(tmp_path: Path) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    pd.DataFrame([{"id": "a", "value": 1, "created_at": "first"}]).to_parquet(first_path, index=False)
    pd.DataFrame([{"id": "a", "value": 1, "created_at": "second"}]).to_parquet(second_path, index=False)

    first = pd.DataFrame([fingerprint_dataset(DatasetSpec("sample", (first_path,), ("id",)), pass_name="first")])
    second = pd.DataFrame([fingerprint_dataset(DatasetSpec("sample", (second_path,), ("id",)), pass_name="second")])

    comparison = compare_fingerprints(first, second).iloc[0]

    assert comparison["unchanged"]
    assert comparison["duplicate_keys_after"] == 0
    assert comparison["null_keys_after"] == 0


def test_fingerprint_reports_duplicate_stable_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.parquet"
    pd.DataFrame([{"id": "a", "value": 1}, {"id": "a", "value": 2}]).to_parquet(path, index=False)

    result = fingerprint_dataset(DatasetSpec("sample", (path,), ("id",)), pass_name="first")

    assert result["duplicate_keys"] == 1


def test_prepare_isolated_project_rewrites_derived_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    configs = project_root / "configs"
    configs.mkdir(parents=True)
    config_path = configs / "project.yaml"
    config_path.write_text("project_name: test\n", encoding="utf-8")
    (configs / "player_rosters.yaml").write_text("teams: []\n", encoding="utf-8")
    run_root = project_root / "data" / "validation_runs" / "run_001"

    isolated = prepare_isolated_project(project_root, config_path, run_root)
    content = yaml.safe_load(isolated.read_text(encoding="utf-8"))

    assert Path(content["parsed_silver_dir"]).is_absolute()
    assert run_root.resolve() in Path(content["parsed_silver_dir"]).resolve().parents
    assert Path(content["team_registry_path"]) == run_root.resolve() / "configs" / "player_rosters.yaml"


def test_retention_recovery_restores_only_isolated_demo(tmp_path: Path) -> None:
    run_root = tmp_path / "run_001"
    output_dir = run_root / "data" / "raw" / "demos" / "Vitality" / "archive_1"
    output_dir.mkdir(parents=True)
    archive_path = tmp_path / "archive_1.zip"
    payload = b"demo-content"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("match_mirage.dem", payload)
    demo_path = output_dir / "archive_1_match_mirage.dem"
    demo_path.write_bytes(payload)
    expected_hash = hashlib.sha256(payload).hexdigest()
    manifest = pd.DataFrame(
        [
            {
                "local_archive_id": "archive_1",
                "dem_file_id": "demo_1",
                "dem_path": str(demo_path),
                "archive_path": str(archive_path),
                "dem_sha256": expected_hash,
                "parse_eligible": True,
                "is_merged_demo": False,
            }
        ]
    )

    audit = run_retention_recovery(manifest, run_root=run_root, run_id="run_001").iloc[0]

    assert audit["status"] == "passed"
    assert demo_path.read_bytes() == payload
