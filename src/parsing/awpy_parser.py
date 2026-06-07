from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ParsedDemo:
    tables: dict[str, pd.DataFrame]
    events: dict[str, pd.DataFrame]
    parser_version: str | None


class AwpyParser:
    def __init__(self, *, player_props: list[str], parse_tables: list[str], parse_events: bool = True) -> None:
        self.player_props = player_props
        self.parse_tables = parse_tables
        self.parse_events = parse_events

    def parse(self, dem_path: Path) -> ParsedDemo:
        try:
            from awpy import Demo
        except ImportError as exc:
            raise RuntimeError("Awpy is not installed. Install dependencies with `pip install -r requirements.txt`.") from exc

        demo = Demo(str(dem_path), verbose=True)
        demo.parse(player_props=self.player_props)

        tables = {table_name: to_pandas(getattr(demo, table_name, None)) for table_name in self.parse_tables}
        events = normalize_events(getattr(demo, "events", None)) if self.parse_events else {}
        return ParsedDemo(tables=tables, events=events, parser_version=parser_version())


def parser_version() -> str | None:
    try:
        return metadata.version("awpy")
    except metadata.PackageNotFoundError:
        return None


def to_pandas(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if hasattr(value, "to_pandas"):
        return value.to_pandas()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        try:
            return pd.DataFrame(value)
        except ValueError:
            return pd.DataFrame([value])
    return pd.DataFrame(value)


def normalize_events(value: Any) -> dict[str, pd.DataFrame]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(name): to_pandas(frame) for name, frame in value.items()}
    return {"events": to_pandas(value)}
