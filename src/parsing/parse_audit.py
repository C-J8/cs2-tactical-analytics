from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils.io import ensure_dir


PARSE_AUDIT_COLUMNS = [
    "parse_id",
    "table_name",
    "row_count",
    "column_count",
    "columns",
    "has_series_id",
    "has_map_name",
    "has_target_team",
    "has_opponent",
    "has_tick",
    "has_X",
    "has_Y",
    "has_Z",
    "notes",
    "created_at",
]


def build_parse_audit(silver_dir: Path) -> pd.DataFrame:
    rows = []
    created_at = datetime.now(timezone.utc).isoformat()
    for path in sorted(silver_dir.glob("*.parquet"), key=lambda item: item.name.lower()):
        table_name = path.stem
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            rows.append(error_row(table_name, str(exc), created_at))
            continue
        columns = list(df.columns)
        rows.append(
            {
                "parse_id": "silver_consolidated",
                "table_name": table_name,
                "row_count": len(df),
                "column_count": len(columns),
                "columns": ",".join(columns),
                "has_series_id": "series_id" in columns,
                "has_map_name": "map_name" in columns,
                "has_target_team": "target_team" in columns,
                "has_opponent": "opponent" in columns,
                "has_tick": "tick" in columns,
                "has_X": "X" in columns,
                "has_Y": "Y" in columns,
                "has_Z": "Z" in columns,
                "notes": None,
                "created_at": created_at,
            }
        )
    return pd.DataFrame(rows, columns=PARSE_AUDIT_COLUMNS)


def error_row(table_name: str, message: str, created_at: str) -> dict[str, object]:
    return {
        "parse_id": "silver_consolidated",
        "table_name": table_name,
        "row_count": 0,
        "column_count": 0,
        "columns": "",
        "has_series_id": False,
        "has_map_name": False,
        "has_target_team": False,
        "has_opponent": False,
        "has_tick": False,
        "has_X": False,
        "has_Y": False,
        "has_Z": False,
        "notes": message,
        "created_at": created_at,
    }


def write_parse_audit(silver_dir: Path, output_dir: Path, formats: list[str]) -> dict[str, Path]:
    ensure_dir(output_dir)
    audit = build_parse_audit(silver_dir)
    outputs: dict[str, Path] = {}
    if "csv" in formats:
        csv_path = output_dir / "parse_audit.csv"
        audit.to_csv(csv_path, index=False)
        outputs["parse_audit_csv"] = csv_path
    if "parquet" in formats:
        parquet_path = output_dir / "parse_audit.parquet"
        audit.to_parquet(parquet_path, index=False)
        outputs["parse_audit_parquet"] = parquet_path
    return outputs
