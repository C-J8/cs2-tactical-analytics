from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config.schemas import load_maps_config, load_project_config, load_teams_config
from src.ingestion.hltv_client import HltvClient, build_match_url, enrich_row_with_html, parse_match_page
from src.ingestion.manual_loader import load_manual_matches
from src.ingestion.match_discovery import DISCOVERY_STATUS_COLUMNS, discover_matches
from src.ingestion.validators import transform_match_catalog
from src.utils.io import write_bronze_snapshot, write_catalog, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.text import clean_string


def build_catalog(
    config_path: Path,
    *,
    target_map: str | None = None,
    target_team: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    if target_map:
        project = project.model_copy(update={"target_maps": [target_map]})
    if target_team:
        project = project.model_copy(update={"target_teams": [target_team]})
    config_dir = config_path.parent
    teams = load_teams_config(config_dir / "teams.yaml")
    maps = load_maps_config(config_dir / "maps.yaml")

    manual_df = load_manual_matches(project.manual_seed_path, required=project.mode == "manual")
    discovered_df = pd.DataFrame()
    discovery_status = pd.DataFrame(columns=DISCOVERY_STATUS_COLUMNS)
    outputs: dict[str, Path] = {}

    if project.mode in {"scrape", "hybrid"}:
        discovered_df, discovery_status = discover_matches(project, teams, maps)
        outputs.update(
            {
                f"discovery_{label}": path
                for label, path in write_dataframe_outputs(
                    {"match_discovery_manifest": discovery_status},
                    project.match_discovery_manifest_dir,
                    force=True,
                    formats=tuple(project.output_formats),
                ).items()
            }
        )

    frames: list[pd.DataFrame] = []
    if not discovered_df.empty:
        frames.append(discovered_df)
    if project.mode in {"manual", "hybrid"} and not manual_df.empty:
        frames.append(enrich_with_scraping(manual_df, project) if project.mode == "hybrid" else manual_df)
    raw_df = pd.concat(frames, ignore_index=True) if frames else manual_df.iloc[0:0].copy()
    write_bronze_snapshot(raw_df, project.bronze_output_dir)

    default_source = "scrape" if project.mode == "scrape" else "manual"
    catalog = transform_match_catalog(raw_df, project, teams, maps, source_method=default_source)
    outputs.update(write_catalog(catalog, project.silver_output_dir, project.output_formats))
    summary = {
        "total_read": len(raw_df),
        "total_manual_read": len(manual_df),
        "total_discovered_rows": len(discovered_df),
        "discovery_requests_failed": int((discovery_status["status"] != "ok").sum()) if not discovery_status.empty else 0,
        "total_after_filters": len(catalog),
        "total_ok": int((catalog["validation_status"] == "ok").sum()) if not catalog.empty else 0,
        "total_warnings": int((catalog["validation_status"] == "warning").sum()) if not catalog.empty else 0,
    }
    return catalog, outputs, summary


def enrich_with_scraping(raw_df: pd.DataFrame, project) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df

    client = HltvClient(
        project.hltv_cache_dir,
        cache_enabled=project.cache_enabled,
        rate_limit_seconds=project.rate_limit_seconds,
    )
    enriched_rows = []
    for _, row in raw_df.iterrows():
        row_dict = row.to_dict()
        row_dict["source_method"] = "manual"
        match_url = clean_string(row_dict.get("match_url")) or build_match_url(clean_string(row_dict.get("hltv_match_id")))
        if not match_url:
            row_dict["scraped_at"] = None
            row_dict["source_html_path"] = None
            enriched_rows.append(row_dict)
            continue

        fetch_result = client.fetch_match_page(match_url, clean_string(row_dict.get("hltv_match_id")))
        if not fetch_result.html:
            row_dict["source_html_path"] = str(fetch_result.html_path) if fetch_result.html_path else None
            row_dict["scraped_at"] = None
            enriched_rows.append(row_dict)
            continue

        parsed = parse_match_page(fetch_result.html)
        enriched = enrich_row_with_html(row_dict, parsed, fetch_result.html_path)
        if _was_enriched(row_dict, enriched):
            enriched["source_method"] = "manual+scrape"
        enriched_rows.append(enriched)

    return pd.DataFrame(enriched_rows)


def _was_enriched(before: dict[str, object], after: dict[str, object]) -> bool:
    fields = ["match_date", "event_name", "team_1", "team_2", "map_name", "map_number", "demo_link"]
    return any(clean_string(before.get(field)) != clean_string(after.get(field)) for field in fields)


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Match catalog build summary")
    print(f"- total de linhas lidas: {summary['total_read']}")
    print(f"- total do seed manual: {summary['total_manual_read']}")
    print(f"- total descoberto automaticamente: {summary['total_discovered_rows']}")
    print(f"- requisicoes de descoberta com falha/bloqueio: {summary['discovery_requests_failed']}")
    print(f"- total apos filtros: {summary['total_after_filters']}")
    print(f"- total validation_status = ok: {summary['total_ok']}")
    print(f"- total com warnings: {summary['total_warnings']}")
    for fmt, path in outputs.items():
        print(f"- arquivo {fmt}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the CS2 HLTV match catalog.")
    parser.add_argument("--config", type=Path, required=True, help="Path to configs/project.yaml")
    parser.add_argument("--target-map", default=None, help="Override the configured target map for this run")
    parser.add_argument("--target-team", default=None, help="Override the configured target team for this run")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = build_catalog(args.config, target_map=args.target_map, target_team=args.target_team)
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
