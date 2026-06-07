from __future__ import annotations

from pathlib import Path

import pandas as pd


EXPECTED_MANUAL_COLUMNS = [
    "hltv_match_id",
    "match_url",
    "match_date",
    "event_name",
    "team_1",
    "team_2",
    "map_name",
    "map_number",
    "demo_link",
]


def empty_manual_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPECTED_MANUAL_COLUMNS)


def load_manual_matches(path: Path, *, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Manual seed CSV not found: {path}")
        return empty_manual_frame()

    df = pd.read_csv(path, dtype="string", keep_default_na=False, comment="#")
    for column in EXPECTED_MANUAL_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[EXPECTED_MANUAL_COLUMNS]
