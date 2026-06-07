from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_match_catalog_cli_runs_end_to_end(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    seed_dir = tmp_path / "data" / "raw" / "manual"
    bronze_dir = tmp_path / "data" / "bronze" / "match_catalog_raw"
    silver_dir = tmp_path / "data" / "silver" / "matches_catalog"
    cache_dir = tmp_path / "data" / "raw" / "hltv_pages"
    config_dir.mkdir(parents=True)
    seed_dir.mkdir(parents=True)

    seed_path = seed_dir / "matches_seed.csv"
    seed_path.write_text(
        "\n".join(
            [
                "hltv_match_id,match_url,match_date,event_name,team_1,team_2,map_name,map_number,demo_link",
                "42,https://www.hltv.org/matches/42/example,2026-01-01,Example,Team Vitality,NAVI,de_mirage,1,",
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "project.yaml").write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-06-05"
target_maps:
  - Mirage
target_teams:
  - Vitality
output_formats:
  - csv
  - parquet
rate_limit_seconds: 0
cache_enabled: true
manual_seed_path: {seed_path.as_posix()}
hltv_cache_dir: {cache_dir.as_posix()}
bronze_output_dir: {bronze_dir.as_posix()}
silver_output_dir: {silver_dir.as_posix()}
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "teams.yaml").write_text(
        """
teams:
  - team_name: Vitality
    hltv_team_id: 9565
    aliases:
      - Team Vitality
      - Vitality
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "maps.yaml").write_text(
        """
maps:
  - map_name: Mirage
    aliases:
      - de_mirage
      - Mirage
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "src.ingestion.build_match_catalog", "--config", str(config_dir / "project.yaml")],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total de linhas lidas: 1" in result.stdout
    assert (silver_dir / "matches_catalog.csv").exists()
    assert (silver_dir / "matches_catalog.parquet").exists()
