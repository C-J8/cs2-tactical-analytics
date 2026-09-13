from __future__ import annotations

import argparse
from pathlib import Path

from src.config.schemas import load_project_config
from src.teams.registry import load_team_registry, registry_audit
from src.utils.io import write_dataframe_outputs
from src.utils.logging import configure_logging


def run_team_dictionary_pipeline(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, object], dict[str, Path]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    registry_path = (
        project.team_registry_path
        if project.team_registry_path.is_absolute()
        else project_root / project.team_registry_path
    )
    registry = load_team_registry(registry_path)
    frames = {
        "team_dictionary": registry.team_frame(),
        "player_team_memberships": registry.membership_frame(),
        "team_dictionary_audit": registry_audit(registry),
    }
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_dataframe_outputs(
            frames,
            project_root / "data/gold/reference/team_dictionary",
            force=force,
            formats=tuple(project.output_formats),
        )
    return frames, outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the versioned team and player identity dictionary.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configure_logging()
    frames, outputs = run_team_dictionary_pipeline(args.config, force=args.force, dry_run=args.dry_run)
    print(
        {
            "teams": len(frames["team_dictionary"]),
            "memberships": len(frames["player_team_memberships"]),
            "outputs": {key: str(value) for key, value in outputs.items()},
        }
    )


if __name__ == "__main__":
    main()
