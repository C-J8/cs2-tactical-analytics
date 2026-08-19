from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.config.schemas import load_project_config
from src.features.build_round_features import run_feature_pipeline
from src.features.round_state import run_round_state_pipeline
from src.features.side_datasets import run_side_dataset_pipeline
from src.maps.identity import resolve_map_identity
from src.maps.registry import load_yaml, normalize_id
from src.utils.io import read_catalog
from src.utils.logging import configure_logging
from src.validation.multi_map_gold_gate import capture_scope_fingerprints, run_multi_map_gold_gate


def run_map_pipeline(
    config_path: Path,
    *,
    target_map: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
) -> tuple[dict[str, Any], dict[str, Path]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    target_team = target_team or project.target_teams[0]
    effective_registry_path = map_registry_path if map_registry_path.is_absolute() else project_root / map_registry_path
    if not effective_registry_path.exists() and not map_registry_path.is_absolute() and map_registry_path.exists():
        effective_registry_path = map_registry_path
    identity = resolve_map_identity(target_map, registry_path=effective_registry_path)
    ensure_registry_active(effective_registry_path, identity.map_id)
    if identity.map_id == "inferno":
        ensure_inferno_ready(project_root, target_team=target_team)
    gold_dir = project_root / "data" / "gold"
    validation_dir = gold_dir / "validation" / "multi_map_gold"

    if dry_run:
        return (
            {
                "map_id": identity.map_id,
                "target_team": target_team,
                "dry_run": True,
                "status": "ok",
                "steps": "build_round_features|round_state|side_datasets|multi_map_gold_gate",
            },
            {},
        )

    mirage_before = capture_scope_fingerprints(gold_dir, map_name="Mirage", target_team=target_team, registry_path=effective_registry_path)
    validation_dir.mkdir(parents=True, exist_ok=True)
    mirage_before.to_parquet(validation_dir / "mirage_gold_preservation_before.parquet", index=False)
    _, feature_outputs, feature_summary = run_feature_pipeline(
        config_path,
        force=force,
        dry_run=False,
        target_map=identity.display_name,
        target_team=target_team,
        map_registry_path=effective_registry_path,
    )
    _, _, state_outputs, state_summary = run_round_state_pipeline(
        config_path,
        force=force,
        dry_run=False,
        target_map=identity.display_name,
        target_team=target_team,
        map_registry_path=effective_registry_path,
    )
    _, side_outputs, side_summary = run_side_dataset_pipeline(
        config_path,
        force=force,
        dry_run=False,
        target_map=identity.display_name,
        target_team=target_team,
        map_registry_path=effective_registry_path,
    )
    _, gate_outputs, gate_summary = run_multi_map_gold_gate(
        config_path,
        target_map=identity.display_name,
        target_team=target_team,
        force=True,
        dry_run=False,
        map_registry_path=effective_registry_path,
        mirage_before=mirage_before,
    )

    outputs = {**feature_outputs, **state_outputs, **side_outputs, **gate_outputs}
    summary = {
        "map_id": identity.map_id,
        "target_team": target_team,
        "round_features": feature_summary.get("rounds_generated", 0),
        "round_state_rows": state_summary.get("total_rounds", 0),
        "t_side_all": side_summary.get("t_side_all", 0),
        "ct_side": side_summary.get("ct_side", 0),
        "gate_status": gate_summary.get("overall_status"),
        "status": "ok" if gate_summary.get("overall_status") == "passed" else "warning",
    }
    return summary, outputs


def ensure_registry_active(registry_path: Path, map_id: str) -> None:
    registry = load_yaml(registry_path)
    for entry in registry.get("maps", []):
        if normalize_id(str(entry.get("map_id") or "")) == map_id:
            if str(entry.get("status") or "").casefold() != "active":
                raise ValueError(f"Map registry entry is not active for {map_id}: {entry.get('status')}")
            return
    raise ValueError(f"Map registry entry not found for {map_id}.")


def ensure_inferno_ready(project_root: Path, *, target_team: str) -> None:
    path = project_root / "data" / "gold" / "maps" / "inferno" / "region_mapping" / "inferno_region_mapping_audit.parquet"
    if not path.exists():
        raise FileNotFoundError("Inferno Stage 8.7 audit not found. Run src.maps.build_region_mapping first.")
    audit = read_catalog(path)
    scoped = audit[audit["target_team"].astype(str).str.casefold().eq(target_team.casefold())] if "target_team" in audit.columns else audit
    if scoped.empty or not bool(scoped.iloc[-1].get("ready_for_inferno_feature_run")):
        raise ValueError("Inferno is not ready for feature run according to Stage 8.7 audit.")


def print_summary(summary: dict[str, Any], outputs: dict[str, Path]) -> None:
    print("Scoped map feature pipeline summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the scoped map feature pipeline without EDA, modeling, dashboard, or BigQuery.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    summary, outputs = run_map_pipeline(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        map_registry_path=args.map_registry,
    )
    print_summary(summary, outputs)


if __name__ == "__main__":
    main()
