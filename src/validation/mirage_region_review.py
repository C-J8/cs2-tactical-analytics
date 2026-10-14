from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import yaml
from PIL import Image

from src.config.schemas import load_project_config
from src.ingestion.demo_downloader import sha256_file
from src.utils.io import ensure_dir, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table, now_utc


SEMANTIC_COLORS = {
    "site_a": "#ff7043",
    "site_b": "#42a5f5",
    "a_pressure": "#ffa726",
    "b_pressure": "#26c6da",
    "mid_control": "#ab47bc",
    "ct_space": "#66bb6a",
    "rotation": "#ffee58",
    "t_spawn_area": "#ec407a",
}


def run_region_review_pack(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    map_config_path = project_root / "configs/maps/mirage.yaml"
    map_config = load_yaml(map_config_path)
    manifest_path = project_root / Path(map_config["assets"]["manifest"])
    manifest = pd.read_parquet(manifest_path.with_suffix(".parquet"))
    radar_row = manifest[manifest["resource"].astype(str).eq("images")].iloc[0]
    radar_path = project_root / Path(str(radar_row["local_path"]))
    crosswalk = pd.read_parquet(
        project_root / "data/gold/maps/area_discovery/mirage_place_registry_crosswalk.parquet"
    )
    coordinates = pd.read_parquet(project_root / "data/gold/maps/area_discovery/map_place_coordinates.parquet")
    crosswalk = crosswalk[
        crosswalk["map_id"].astype(str).eq("mirage")
        & crosswalk["target_team"].astype(str).str.casefold().eq(project.target_teams[0].casefold())
    ].copy()
    coordinates = coordinates[
        coordinates["map_id"].astype(str).eq("mirage")
        & coordinates["target_team"].astype(str).str.casefold().eq(project.target_teams[0].casefold())
    ].copy()
    review = build_review_rows(crosswalk, coordinates, map_config)
    summary = build_review_summary(review, map_config, radar_path, expected_hash=str(radar_row["sha256"]))
    frames = {
        "mirage_region_review": review,
        "mirage_region_review_summary": pd.DataFrame([summary]),
    }
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = project_root / "data/gold/validation/mirage_region_review"
        outputs.update(write_dataframe_outputs(frames, output_dir, force=force, formats=tuple(project.output_formats)))
        overlay_path = output_dir / "mirage_region_review_overlay.png"
        if force or not overlay_path.exists():
            write_overlay(review, radar_path, overlay_path)
        outputs["overlay"] = overlay_path
        report_path = project_root / "docs/mirage_region_review.md"
        if force or not report_path.exists():
            report_path.write_text(build_report(review, summary, overlay_path, project_root), encoding="utf-8")
        outputs["report"] = report_path
    return frames, outputs, summary


def build_review_rows(
    crosswalk: pd.DataFrame,
    coordinates: pd.DataFrame,
    map_config: dict[str, Any],
) -> pd.DataFrame:
    merged = crosswalk.merge(
        coordinates[["raw_place", "x_median", "y_median", "z_median"]],
        on="raw_place",
        how="left",
        validate="one_to_one",
    )
    radar = map_config["coordinate_system"]["radar_transform"]
    merged[["radar_x", "radar_y"]] = merged.apply(
        lambda row: pd.Series(world_to_radar(float(row["x_median"]), float(row["y_median"]), radar)),
        axis=1,
    )
    merged["inside_radar"] = (
        merged["radar_x"].between(0, int(radar["width"]))
        & merged["radar_y"].between(0, int(radar["height"]))
    )
    merged["review_status"] = merged.apply(
        lambda row: "ready" if bool(row.get("matched")) and not bool(row.get("ambiguous")) and bool(row["inside_radar"]) else "blocked",
        axis=1,
    )
    return merged[
        [
            "raw_place",
            "tick_count",
            "matched_region_id",
            "matched_region_display_name",
            "semantic_tags",
            "match_source",
            "x_median",
            "y_median",
            "z_median",
            "radar_x",
            "radar_y",
            "inside_radar",
            "matched",
            "ambiguous",
            "review_status",
        ]
    ].sort_values(["matched_region_id", "raw_place"], kind="stable").reset_index(drop=True)


def world_to_radar(x: float, y: float, transform: dict[str, Any]) -> tuple[float, float]:
    scale = float(transform["scale"])
    return (x - float(transform["pos_x"])) / scale, (float(transform["pos_y"]) - y) / scale


def build_review_summary(
    review: pd.DataFrame,
    map_config: dict[str, Any],
    radar_path: Path,
    *,
    expected_hash: str,
) -> dict[str, Any]:
    configured_regions = {str(row["region_id"]) for row in map_config.get("physical_regions", [])}
    observed_regions = set(review["matched_region_id"].dropna().astype(str))
    radar_hash = sha256_file(radar_path) if radar_path.exists() else None
    blocked = int(review["review_status"].ne("ready").sum())
    return {
        "review_id": "mirage_region_review_v1",
        "map_id": "mirage",
        "target_team": "Vitality",
        "configured_regions": len(configured_regions),
        "observed_regions": len(observed_regions),
        "raw_places_reviewed": len(review),
        "unmatched_places": int((~review["matched"].fillna(False)).sum()),
        "ambiguous_places": int(review["ambiguous"].fillna(False).sum()),
        "outside_radar_places": int((~review["inside_radar"].fillna(False)).sum()),
        "missing_configured_regions": "|".join(sorted(configured_regions - observed_regions)),
        "radar_sha256": radar_hash,
        "radar_hash_matches_manifest": radar_hash == expected_hash,
        "automated_prerequisites_passed": blocked == 0 and configured_regions == observed_regions and radar_hash == expected_hash,
        "manual_signoff_required": True,
        "status": "ready_for_manual_signoff" if blocked == 0 and configured_regions == observed_regions and radar_hash == expected_hash else "blocked",
        "created_at": now_utc(),
    }


def write_overlay(review: pd.DataFrame, radar_path: Path, output_path: Path) -> None:
    ensure_dir(output_path.parent)
    image = Image.open(radar_path).convert("RGBA")
    fig, axis = plt.subplots(figsize=(14, 14), dpi=140)
    axis.imshow(image)
    representatives = (
        review.sort_values("tick_count", ascending=False, kind="stable")
        .drop_duplicates("matched_region_id")
        .sort_values("matched_region_id")
    )
    for _, row in representatives.iterrows():
        semantic = str(row.get("semantic_tags") or "")
        color = SEMANTIC_COLORS.get(semantic.split("|")[0], "#ffffff")
        axis.scatter(row["radar_x"], row["radar_y"], s=65, c=color, edgecolors="black", linewidths=0.8)
        axis.annotate(
            str(row["matched_region_id"]),
            (row["radar_x"], row["radar_y"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            color="white",
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "black", "alpha": 0.65, "edgecolor": color},
        )
    axis.set_xlim(0, image.width)
    axis.set_ylim(image.height, 0)
    axis.set_title("Mirage region review — observed place centroids", color="white", fontsize=16)
    axis.axis("off")
    fig.patch.set_facecolor("#111111")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def build_report(review: pd.DataFrame, summary: dict[str, Any], overlay_path: Path, project_root: Path) -> str:
    relative_overlay = overlay_path.relative_to(project_root).as_posix()
    return "\n".join(
        [
            "# Mirage region review",
            "",
            "This pack supports the explicit manual sign-off required by the Mirage consolidation contract.",
            "It combines the pinned Awpy radar, observed player-place centroids, and the canonical region crosswalk.",
            "",
            "## Automated prerequisites",
            "",
            f"- Status: `{summary['status']}`",
            f"- Configured/observed regions: `{summary['configured_regions']}/{summary['observed_regions']}`",
            f"- Raw places reviewed: `{summary['raw_places_reviewed']}`",
            f"- Unmatched / ambiguous / outside radar: `{summary['unmatched_places']} / {summary['ambiguous_places']} / {summary['outside_radar_places']}`",
            f"- Radar hash matches pinned manifest: `{summary['radar_hash_matches_manifest']}`",
            "",
            "## Overlay",
            "",
            f"![Mirage region review overlay](../{relative_overlay})",
            "",
            "## Review table",
            "",
            markdown_table(
                review,
                [
                    "raw_place",
                    "matched_region_id",
                    "semantic_tags",
                    "tick_count",
                    "radar_x",
                    "radar_y",
                    "review_status",
                ],
            ),
            "",
            "## Sign-off rule",
            "",
            "The reviewer must inspect the overlay and table, confirm A/B/mid/CT/rotation placement, and then record their identity, timestamp, reviewed region IDs, and this report path in `configs/quality/mirage_consolidation_evidence.yaml`.",
            "",
        ]
    )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Mirage radar/place review pack.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_region_review_pack(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
    )
    print("Mirage region review summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
